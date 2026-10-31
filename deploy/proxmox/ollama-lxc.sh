#!/usr/bin/env bash
# Coin Vault — Ollama (local AI) container with the NVIDIA GPU, for Proxmox VE.
#
# Run on the Proxmox host as root. The host's NVIDIA driver must already work (nvidia-smi shows the card).
# It creates a Debian LXC, passes the GPU through, installs the matching NVIDIA user-space libraries and
# Ollama, makes Ollama listen on your LAN, and downloads a vision model. Coin Vault then talks to it.
#
#   bash ollama-lxc.sh                       # interactive
#   bash ollama-lxc.sh --yes                 # accept every default
#   bash ollama-lxc.sh --dry-run             # show what would run, change nothing
#   bash ollama-lxc.sh --update-driver 119   # after updating the host's NVIDIA driver: match it in container 119
#
# Options (all optional): --ctid N --hostname NAME --cores N --memory MB --disk GB --storage ID
#   --template-storage ID --bridge vmbr0 --ip dhcp|CIDR --gateway IP --nameserver IP --debian 12|13
#   --model NAME (default gemma4:26b; "none" to skip) --driver-run FILE (the host's NVIDIA .run installer,
#   if it can't be downloaded from NVIDIA)
set -euo pipefail

# --- Defaults ---------------------------------------------------------------------------
CTID=""
CT_HOSTNAME="ollama"
CORES=4
MEMORY=16384
SWAP=2048
DISK=80
STORAGE=""
TPL_STORAGE="local"
BRIDGE="vmbr0"
IP="dhcp"
GATEWAY=""
NAMESERVER=""
DEBIAN=13
MODEL="gemma4:26b"
DRIVER_RUN=""
UPDATE_DRIVER=""
ASSUME_YES=0
DRY_RUN=0

c_info=$'\033[1;36m'; c_ok=$'\033[1;32m'; c_warn=$'\033[1;33m'; c_err=$'\033[1;31m'; c_off=$'\033[0m'
msg()  { printf '%s==>%s %s\n' "$c_info" "$c_off" "$*"; }
ok()   { printf '%s ✓ %s %s\n' "$c_ok" "$c_off" "$*"; }
warn() { printf '%s !  %s%s\n' "$c_warn" "$*" "$c_off"; }
die()  { printf '%sError:%s %s\n' "$c_err" "$c_off" "$*" >&2; exit 1; }

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ctid) CTID="$2"; shift 2 ;;
    --hostname) CT_HOSTNAME="$2"; shift 2 ;;
    --cores) CORES="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --disk) DISK="$2"; shift 2 ;;
    --storage) STORAGE="$2"; shift 2 ;;
    --template-storage) TPL_STORAGE="$2"; shift 2 ;;
    --bridge) BRIDGE="$2"; shift 2 ;;
    --ip) IP="$2"; shift 2 ;;
    --gateway) GATEWAY="$2"; shift 2 ;;
    --nameserver) NAMESERVER="$2"; shift 2 ;;
    --debian) DEBIAN="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --driver-run) DRIVER_RUN="$2"; shift 2 ;;
    --update-driver) UPDATE_DRIVER="$2"; shift 2 ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done

[[ "$DEBIAN" == "12" || "$DEBIAN" == "13" ]] || die "--debian must be 12 or 13"
[[ -z "$DRIVER_RUN" || -f "$DRIVER_RUN" ]] || die "--driver-run: $DRIVER_RUN not found"

run() {
  if (( DRY_RUN )); then printf '   [dry-run] %s\n' "$*"; else "$@"; fi
}

ask() { # ask VAR "Question" default
  local __var=$1 __q=$2 __def=$3 __ans=""
  if (( ASSUME_YES )); then printf -v "$__var" '%s' "$__def"; return; fi
  read -rp "$__q [$__def]: " __ans
  printf -v "$__var" '%s' "${__ans:-$__def}"
}

# --- The host's GPU ---------------------------------------------------------------------
if (( DRY_RUN )); then
  DRIVER="610.57.04"
else
  [[ $EUID -eq 0 ]] || die "run as root on the Proxmox host"
  command -v pct >/dev/null && command -v pveam >/dev/null || die "pct/pveam not found: run this on a Proxmox VE host"
  command -v nvidia-smi >/dev/null || die "nvidia-smi not found: install the NVIDIA driver on the Proxmox host first"
  DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1 | tr -d ' ')
  [[ "$DRIVER" =~ ^[0-9]+(\.[0-9]+)+$ ]] || die "couldn't read the driver version from nvidia-smi"
fi

# /dev/nvidia-uvm (CUDA needs it) only appears once its module is loaded; load it now and at every boot.
ensure_uvm() {
  if (( DRY_RUN )); then
    run modprobe nvidia-uvm
    return
  fi
  modprobe nvidia-uvm 2>/dev/null || true
  if [[ ! -e /dev/nvidia-uvm ]]; then
    if command -v nvidia-modprobe >/dev/null; then
      nvidia-modprobe -u -c=0 || true
    else
      MAJOR=$(awk '$2=="nvidia-uvm" {print $1}' /proc/devices)
      [[ -n "$MAJOR" ]] && mknod -m 666 /dev/nvidia-uvm c "$MAJOR" 0 && mknod -m 666 /dev/nvidia-uvm-tools c "$MAJOR" 1
    fi
  fi
  [[ -e /dev/nvidia-uvm ]] || die "/dev/nvidia-uvm is missing even after loading nvidia-uvm; check the driver install"
  echo nvidia-uvm > /etc/modules-load.d/nvidia-uvm.conf
  if command -v nvidia-modprobe >/dev/null && [[ ! -f /etc/udev/rules.d/70-nvidia-uvm.rules ]]; then
    printf '%s\n' 'KERNEL=="nvidia_uvm", RUN+="/bin/sh -c '"'"'nvidia-modprobe -c0 -u'"'"'"' > /etc/udev/rules.d/70-nvidia-uvm.rules
  fi
}

# The NVIDIA user-space libraries in the container must be the same version as the host's kernel driver.
install_userspace() { # install_userspace CTID
  local id=$1 url="https://us.download.nvidia.com/XFree86/Linux-x86_64/$DRIVER/NVIDIA-Linux-x86_64-$DRIVER.run"
  msg "Installing NVIDIA $DRIVER user-space libraries in container $id (no kernel module)"
  if [[ -n "$DRIVER_RUN" ]]; then
    run pct push "$id" "$DRIVER_RUN" /root/nvidia.run --perms 755
  else
    run pct exec "$id" -- curl -fL --retry 3 -o /root/nvidia.run "$url" \
      || die "couldn't download $url. Copy the installer you used on the host and re-run with --driver-run /path/to/NVIDIA-Linux-x86_64-$DRIVER.run"
  fi
  run pct exec "$id" -- sh /root/nvidia.run --silent --no-kernel-module --no-questions --ui=none --no-x-check --no-nouveau-check \
    || die "the NVIDIA installer failed inside the container; see /var/log/nvidia-installer.log there (pct enter $id)"
  run pct exec "$id" -- rm -f /root/nvidia.run
  run pct exec "$id" -- nvidia-smi -L || die "nvidia-smi doesn't see the GPU inside the container"
  ok "the container sees the GPU"
}

if [[ -n "$UPDATE_DRIVER" ]]; then
  [[ "$UPDATE_DRIVER" =~ ^[0-9]+$ ]] || die "--update-driver needs a container ID"
  ensure_uvm
  install_userspace "$UPDATE_DRIVER"
  run pct exec "$UPDATE_DRIVER" -- systemctl restart ollama
  ok "container $UPDATE_DRIVER now matches driver $DRIVER"
  exit 0
fi

printf '\n%sOllama with the GPU — Proxmox LXC installer%s\n' "$c_ok" "$c_off"
echo "Creates a Debian container with the NVIDIA GPU passed through and Ollama listening on your LAN."
(( DRY_RUN )) || nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader | sed 's/^/   GPU /'
echo "   Host driver $DRIVER"
echo

# --- Questions --------------------------------------------------------------------------
if [[ -z "$CTID" ]]; then
  NEXT=$(pvesh get /cluster/nextid 2>/dev/null || echo 100)
  ask CTID "Container ID" "$NEXT"
fi
[[ "$CTID" =~ ^[0-9]+$ ]] || die "container ID must be a number"
if (( ! DRY_RUN )) && pct status "$CTID" >/dev/null 2>&1; then die "container $CTID already exists"; fi

ask CT_HOSTNAME "Hostname" "$CT_HOSTNAME"
ask CORES "CPU cores" "$CORES"
ask MEMORY "Memory (MB)" "$MEMORY"
ask DISK "Root disk (GB; models are 5-20 GB each)" "$DISK"
if [[ -z "$STORAGE" ]]; then
  CANDIDATES=$(pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}' || true)
  DEFAULT_STORAGE=$(echo "$CANDIDATES" | grep -m1 -x 'local-lvm' || echo "$CANDIDATES" | head -n1)
  [[ -n "$CANDIDATES" ]] && echo "Storage for containers: $(echo "$CANDIDATES" | xargs)"
  ask STORAGE "Storage for the container disk" "${DEFAULT_STORAGE:-local-lvm}"
fi
ask BRIDGE "Network bridge" "$BRIDGE"
ask IP "IPv4 address, dhcp or CIDR such as 192.168.1.80/24" "$IP"
if [[ "$IP" != "dhcp" ]]; then
  [[ "$IP" == */* ]] || die "a static address needs a prefix length, e.g. 192.168.1.80/24"
  ask GATEWAY "Gateway" "${GATEWAY:-${IP%.*}.1}"
  ask NAMESERVER "DNS server" "${NAMESERVER:-$GATEWAY}"
fi
ask MODEL "Vision model to download (none to skip)" "$MODEL"

NET="name=eth0,bridge=$BRIDGE,ip=$IP"
[[ -n "$GATEWAY" ]] && NET="$NET,gw=$GATEWAY"

DEVICES=()
if (( DRY_RUN )); then
  DEVICES=(/dev/nvidia0 /dev/nvidiactl /dev/nvidia-uvm /dev/nvidia-uvm-tools)
else
  ensure_uvm
  for d in /dev/nvidia[0-9]* /dev/nvidiactl /dev/nvidia-uvm /dev/nvidia-uvm-tools /dev/nvidia-caps/nvidia-cap1 /dev/nvidia-caps/nvidia-cap2; do
    [[ -c "$d" ]] && DEVICES+=("$d")
  done
fi

echo
msg "Summary"
cat <<EOF
   Container   $CTID ($CT_HOSTNAME), Debian $DEBIAN, unprivileged
   Resources   $CORES cores, ${MEMORY} MB RAM, ${DISK} GB on $STORAGE
   Network     $BRIDGE, $IP${GATEWAY:+ via $GATEWAY}${NAMESERVER:+, DNS $NAMESERVER}
   GPU         ${DEVICES[*]}
   NVIDIA      $DRIVER user-space libraries (matching the host)
   Model       $MODEL
EOF
if (( ! ASSUME_YES )); then
  read -rp "Create it? [Y/n]: " GO
  [[ "${GO:-y}" =~ ^[Yy] ]] || die "cancelled"
fi

# --- Template ---------------------------------------------------------------------------
msg "Finding the Debian $DEBIAN template"
if (( DRY_RUN )); then
  TEMPLATE="debian-$DEBIAN-standard_$DEBIAN.x_amd64.tar.zst"
else
  pveam update >/dev/null || warn "pveam update failed; using the cached template list"
  TEMPLATE=$(pveam available --section system | awk '{print $2}' | grep -E "^debian-$DEBIAN-standard_.*amd64" | sort -V | tail -n1)
  [[ -n "$TEMPLATE" ]] || die "no Debian $DEBIAN template found in 'pveam available'"
fi
if (( DRY_RUN )) || ! pveam list "$TPL_STORAGE" | grep -q "$TEMPLATE"; then
  run pveam download "$TPL_STORAGE" "$TEMPLATE"
fi
ok "template $TEMPLATE"

# --- Container --------------------------------------------------------------------------
msg "Creating container $CTID"
CREATE=(pct create "$CTID" "$TPL_STORAGE:vztmpl/$TEMPLATE"
  --hostname "$CT_HOSTNAME" --ostype debian --unprivileged 1 --features nesting=1
  --cores "$CORES" --memory "$MEMORY" --swap "$SWAP"
  --rootfs "$STORAGE:$DISK" --net0 "$NET" --onboot 1 --tags "coinvault;ai")
[[ -n "$NAMESERVER" ]] && CREATE+=(--nameserver "$NAMESERVER")
i=0
for d in "${DEVICES[@]}"; do
  CREATE+=("--dev$i" "$d,mode=0666")  # device passthrough (Proxmox VE 8.1 or newer)
  i=$((i + 1))
done
run "${CREATE[@]}" || die "pct create failed. Device passthrough (--devN) needs Proxmox VE 8.1 or newer: pveversion shows yours"
run pct start "$CTID"
ok "container created and started"

msg "Waiting for the network inside the container"
NET_WAIT='for i in $(seq 1 180); do
  getent hosts deb.debian.org >/dev/null && exit 0
  if [ "$i" = 45 ] && ! ip -4 addr show eth0 | grep -q inet; then
    systemctl restart networking 2>/dev/null || ifup eth0 2>/dev/null || true
  fi
  sleep 1
done; exit 1'
run pct exec "$CTID" -- bash -c "$NET_WAIT" \
  || die "the container has no network/DNS after 3 minutes (remove this attempt with: pct stop $CTID; pct destroy $CTID)"
ok "network is up"

msg "Installing base packages"
run pct exec "$CTID" -- bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -q && apt-get install -y -q curl ca-certificates pciutils kmod zstd'

install_userspace "$CTID"

# --- Ollama -----------------------------------------------------------------------------
msg "Installing Ollama (https://ollama.com/install.sh)"
run pct exec "$CTID" -- bash -c 'curl -fsSL https://ollama.com/install.sh | sh' || die "the Ollama installer failed"
OVERRIDE=$(mktemp)
trap 'rm -f "$OVERRIDE"' EXIT
cat > "$OVERRIDE" <<'EOF'
# Coin Vault: listen on the LAN (Ollama has no sign-in; keep it on your private network) and keep a
# model loaded for 30 minutes after its last use, so a batch of photos doesn't reload it each time.
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=30m"
EOF
run pct exec "$CTID" -- mkdir -p /etc/systemd/system/ollama.service.d
run pct push "$CTID" "$OVERRIDE" /etc/systemd/system/ollama.service.d/override.conf --perms 644
run pct exec "$CTID" -- bash -c 'systemctl daemon-reload && systemctl enable ollama && systemctl restart ollama'
run pct exec "$CTID" -- bash -c 'for i in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/version && exit 0; sleep 1; done; exit 1' \
  || die "Ollama didn't start; see: pct exec $CTID -- journalctl -u ollama -n 50"
echo
ok "Ollama is running"

if [[ "$MODEL" != "none" && -n "$MODEL" ]]; then
  msg "Downloading $MODEL (this can take a while)"
  run pct exec "$CTID" -- ollama pull "$MODEL" || warn "the download failed; retry with: pct exec $CTID -- ollama pull $MODEL"
  msg "Loading it once to check it runs on the GPU"
  run pct exec "$CTID" -- bash -c "curl -s http://127.0.0.1:11434/api/generate -d '{\"model\": \"$MODEL\", \"prompt\": \"Say OK\", \"stream\": false}' >/dev/null; ollama ps" || true
  echo "   The PROCESSOR column above should say 100% GPU."
fi

if (( DRY_RUN )); then
  CT_IP="<container-ip>"
else
  CT_IP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
fi
run pct set "$CTID" --description "Ollama for Coin Vault: http://$CT_IP:11434 (private LAN only). After a host NVIDIA driver update: ollama-lxc.sh --update-driver $CTID"

echo
ok "Ollama is ready in container $CTID"
echo "   Address   http://$CT_IP:11434"
echo "   In Coin Vault: Settings, AI: enter that address, press Check the server, then Use this model."
echo "   Models    pct exec $CTID -- ollama list"
echo "   GPU       pct exec $CTID -- nvidia-smi"
echo
warn "Ollama has no password. Keep this container on your private network and don't forward port 11434."
warn "When you update the NVIDIA driver on the host, run: bash ollama-lxc.sh --update-driver $CTID"
