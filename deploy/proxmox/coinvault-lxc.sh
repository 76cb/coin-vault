#!/usr/bin/env bash
# Coin Vault — Proxmox helper script.
#
# Run on the Proxmox VE host as root. It creates a Debian 13 LXC, clones Coin Vault into it
# and runs the native installer (PostgreSQL 16, Python, nginx, systemd). Asks a few questions;
# press Enter to accept each default.
#
#   bash coinvault-lxc.sh                 # interactive
#   bash coinvault-lxc.sh --yes           # accept every default (a random admin password is printed at the end)
#   bash coinvault-lxc.sh --dry-run       # show what would run, change nothing
#
# Options (all optional): --ctid N --hostname NAME --cores N --memory MB --disk GB --storage ID
#   --template-storage ID --bridge vmbr0 --ip dhcp|CIDR --gateway IP --media-disk GB
#   --repo URL --branch NAME --admin USER
# Secrets can be given in the environment instead of prompts:
#   GITHUB_TOKEN (read access to the private repo), CV_ADMIN_PASSWORD.
set -euo pipefail

# --- Defaults ---------------------------------------------------------------------------
CTID=""
CT_HOSTNAME="coinvault"
CORES=2
MEMORY=2048
SWAP=512
DISK=16
STORAGE=""
TPL_STORAGE="local"
BRIDGE="vmbr0"
IP="dhcp"
GATEWAY=""
MEDIA_DISK=0
REPO="https://github.com/76cb/coin-vault.git"
BRANCH="main"
ADMIN_USER="admin"
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
    --media-disk) MEDIA_DISK="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --admin) ADMIN_USER="$2"; shift 2 ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) die "unknown option $1 (see --help)" ;;
  esac
done

# Run a command, or only print it in --dry-run mode. Secrets never pass through here.
run() {
  if (( DRY_RUN )); then printf '   [dry-run] %s\n' "$*"; else "$@"; fi
}

ask() { # ask VAR "Question" default
  local __var=$1 __q=$2 __def=$3 __ans=""
  if (( ASSUME_YES )); then printf -v "$__var" '%s' "$__def"; return; fi
  read -rp "$__q [$__def]: " __ans
  printf -v "$__var" '%s' "${__ans:-$__def}"
}

ask_secret() { # ask_secret VAR "Question"
  local __var=$1 __q=$2 __ans=""
  read -rsp "$__q: " __ans; echo
  printf -v "$__var" '%s' "$__ans"
}

# --- Checks -----------------------------------------------------------------------------
if (( ! DRY_RUN )); then
  [[ $EUID -eq 0 ]] || die "run as root on the Proxmox host"
  command -v pct >/dev/null && command -v pveam >/dev/null || die "pct/pveam not found: run this on a Proxmox VE host"
fi

printf '\n%sCoin Vault — Proxmox LXC installer%s\n' "$c_ok" "$c_off"
echo "Creates a Debian 13 container and installs Coin Vault into it. Keep it on your private LAN only."
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
ask DISK "Root disk (GB)" "$DISK"

if [[ -z "$STORAGE" ]]; then
  CANDIDATES=$(pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}' || true)
  DEFAULT_STORAGE=$(echo "$CANDIDATES" | grep -m1 -x 'local-lvm' || echo "$CANDIDATES" | head -n1)
  [[ -n "$CANDIDATES" ]] && echo "Storage for containers: $(echo "$CANDIDATES" | xargs)"
  ask STORAGE "Storage for the container disk" "${DEFAULT_STORAGE:-local-lvm}"
fi

ask MEDIA_DISK "Separate disk for photos and documents in GB (0 = keep them on the root disk)" "$MEDIA_DISK"
ask BRIDGE "Network bridge" "$BRIDGE"
ask IP "IPv4 address, dhcp or CIDR such as 192.168.1.50/24" "$IP"
if [[ "$IP" != "dhcp" ]]; then
  [[ "$IP" == */* ]] || die "a static address needs a prefix length, e.g. 192.168.1.50/24"
  ask GATEWAY "Gateway" "${GATEWAY:-${IP%.*}.1}"
fi
ask ADMIN_USER "Coin Vault admin username" "$ADMIN_USER"

ADMIN_PASSWORD="${CV_ADMIN_PASSWORD:-}"
GENERATED_PW=0
if [[ -z "$ADMIN_PASSWORD" ]]; then
  if (( ASSUME_YES )); then
    ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
    GENERATED_PW=1
  else
    while true; do
      ask_secret ADMIN_PASSWORD "Coin Vault admin password (10+ characters)"
      (( ${#ADMIN_PASSWORD} >= 10 )) || { warn "too short"; continue; }
      ask_secret PW2 "Repeat the password"
      [[ "$ADMIN_PASSWORD" == "$PW2" ]] && break
      warn "passwords do not match"
    done
  fi
fi
(( ${#ADMIN_PASSWORD} >= 10 )) || die "the admin password must be at least 10 characters"

TOKEN="${GITHUB_TOKEN:-}"
KEEP_TOKEN="y"
if [[ -z "$TOKEN" && $ASSUME_YES -eq 0 ]]; then
  echo
  echo "The repository is private. Paste a GitHub token with read access to it"
  echo "(fine-grained token, Contents: Read-only). Leave empty if the repo is public."
  ask_secret TOKEN "GitHub token"
fi
if [[ -n "$TOKEN" && $ASSUME_YES -eq 0 ]]; then
  ask KEEP_TOKEN "Keep the token in the container so update.sh can pull updates? (y/n)" "y"
fi

NET="name=eth0,bridge=$BRIDGE,ip=$IP"
[[ -n "$GATEWAY" ]] && NET="$NET,gw=$GATEWAY"

echo
msg "Summary"
cat <<EOF
   Container   $CTID ($CT_HOSTNAME), Debian 13, unprivileged
   Resources   $CORES cores, ${MEMORY} MB RAM, ${DISK} GB on $STORAGE$( (( MEDIA_DISK > 0 )) && echo ", ${MEDIA_DISK} GB media disk" )
   Network     $BRIDGE, $IP${GATEWAY:+ via $GATEWAY}
   Source      $REPO ($BRANCH)${TOKEN:+, with token}
   Admin       $ADMIN_USER
EOF
if (( ! ASSUME_YES )); then
  read -rp "Create it? [Y/n]: " GO
  [[ "${GO:-y}" =~ ^[Yy] ]] || die "cancelled"
fi

# --- Template ---------------------------------------------------------------------------
msg "Finding the Debian 13 template"
if (( DRY_RUN )); then
  TEMPLATE="debian-13-standard_13.x_amd64.tar.zst"
else
  pveam update >/dev/null || warn "pveam update failed; using the cached template list"
  TEMPLATE=$(pveam available --section system | awk '{print $2}' | grep -E '^debian-13-standard_.*amd64' | sort -V | tail -n1)
  [[ -n "$TEMPLATE" ]] || die "no Debian 13 template found in 'pveam available'"
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
  --rootfs "$STORAGE:$DISK" --net0 "$NET" --onboot 1 --tags coinvault)
(( MEDIA_DISK > 0 )) && CREATE+=(--mp0 "$STORAGE:$MEDIA_DISK,mp=/var/lib/coinvault")
run "${CREATE[@]}"
run pct start "$CTID"
ok "container created and started"

msg "Waiting for the network inside the container"
run pct exec "$CTID" -- bash -c 'for i in $(seq 1 90); do getent hosts deb.debian.org >/dev/null && exit 0; sleep 1; done; exit 1' \
  || die "the container has no network/DNS; check the bridge and IP settings"
ok "network is up"

msg "Installing git"
run pct exec "$CTID" -- bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -q && apt-get install -y -q git ca-certificates'

# Secrets go into the container as root-only files via pct push, never on a command line.
SECRETS=$(mktemp -d)
trap 'rm -rf "$SECRETS"' EXIT
chmod 700 "$SECRETS"
printf '%s\n' "$ADMIN_PASSWORD" > "$SECRETS/admin-pw"

if [[ -n "$TOKEN" ]]; then
  HOST=$(echo "$REPO" | sed -E 's#^https://([^/]+)/.*#\1#')
  printf 'https://x-access-token:%s@%s\n' "$TOKEN" "$HOST" > "$SECRETS/git-credentials"
  run pct push "$CTID" "$SECRETS/git-credentials" /root/.git-credentials --perms 600
  run pct exec "$CTID" -- git config --global credential.helper store
fi

msg "Cloning $REPO"
run pct exec "$CTID" -- git clone --branch "$BRANCH" "$REPO" /opt/coinvault/app || die "clone failed; check the token and repository URL"
if [[ -n "$TOKEN" && ! "$KEEP_TOKEN" =~ ^[Yy] ]]; then
  run pct exec "$CTID" -- bash -c 'rm -f /root/.git-credentials; git config --global --unset credential.helper'
  warn "token removed; update.sh will ask for credentials when it pulls"
fi
ok "code in /opt/coinvault/app"

msg "Running the Coin Vault installer (this takes a few minutes)"
run pct push "$CTID" "$SECRETS/admin-pw" /root/.cv-admin-pw --perms 600
run pct exec "$CTID" -- env CV_ADMIN_USER="$ADMIN_USER" CV_ADMIN_PASSWORD_FILE=/root/.cv-admin-pw \
  bash /opt/coinvault/app/deploy/lxc/install.sh \
  || die "the installer failed; open the container with 'pct enter $CTID' and see the output above"

if (( DRY_RUN )); then
  CT_IP="<container-ip>"
else
  CT_IP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
fi
run pct set "$CTID" --description "Coin Vault: http://$CT_IP/  (private LAN only). Update with /opt/coinvault/app/deploy/lxc/update.sh"

echo
ok "Coin Vault is running in container $CTID"
echo "   Open      http://$CT_IP/"
echo "   Sign in   $ADMIN_USER"
(( GENERATED_PW )) && echo "   Password  $ADMIN_PASSWORD   (generated; change it in Settings)"
echo "   Shell     pct enter $CTID"
echo "   Update    pct snapshot $CTID before-update && pct exec $CTID -- /opt/coinvault/app/deploy/lxc/update.sh"
echo
warn "Keep this container on your private network. Do not forward ports to it."
