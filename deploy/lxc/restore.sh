#!/usr/bin/env bash
# Put a Coin Vault backup back: the database is replaced and missing photos and documents are copied in.
#
#     /opt/coinvault/app/deploy/lxc/restore.sh                     # list the backups
#     /opt/coinvault/app/deploy/lxc/restore.sh 2026-10-31T071500Z  # restore one of them
#     /opt/coinvault/app/deploy/lxc/restore.sh /root/coinvault-backup-2026-10-31T071500Z.tar   # or a downloaded copy
#
# The current state is backed up first, so a restore can itself be undone.
set -euo pipefail

APP_DIR=/opt/coinvault/app
VENV=/opt/coinvault/venv
ENV_FILE=/etc/coinvault/coinvault.env
WORK=/var/lib/coinvault/restore-tmp

as_app() { sudo -u coinvault bash -c 'set -a; . "$0"; set +a; cd /opt/coinvault/app/backend; exec "$@"' "$ENV_FILE" "$@"; }

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

if [[ $# -eq 0 ]]; then
  LIST="$(as_app "$VENV/bin/python" -m app.cli list-backups)"
  echo "$LIST"
  NEWEST="$(awk 'NF {print $1; exit}' <<<"$LIST")"
  echo
  if [[ -n "$NEWEST" && "$NEWEST" != No* ]]; then
    echo "To put one back, give its name, for example:"
    echo "    $0 $NEWEST"
    echo "or the path of a downloaded coinvault-backup-*.tar file. You'll be asked before anything changes."
  fi
  exit 0
fi

SOURCE="$1"
if [[ -f "$SOURCE" ]]; then
  # a downloaded archive: put a copy where the coinvault user can read it
  rm -rf "$WORK"; install -d -o coinvault -g coinvault -m 0750 "$WORK"
  install -o coinvault -g coinvault -m 0640 "$SOURCE" "$WORK/backup.tar"
  SOURCE="$WORK/backup.tar"
fi

echo "This replaces the whole collection with the backup $1."
read -r -p "Type yes to continue: " answer
[[ "$answer" == "yes" ]] || { echo "Nothing changed."; exit 1; }

echo "==> Backing up the current state first (so this can be undone)"
as_app "$VENV/bin/python" -m app.cli backup

echo "==> Stopping Coin Vault"
systemctl stop coinvault

echo "==> Restoring"
if ! as_app "$VENV/bin/python" -m app.cli restore "$SOURCE" --yes; then
  echo "The restore failed; nothing was started. The backup made a moment ago holds the state from before." >&2
  rm -rf "$WORK"
  exit 1
fi
rm -rf "$WORK"
chmod -R g+rX /var/lib/coinvault/media

echo "==> Starting Coin Vault"
systemctl start coinvault
for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8000/api/v1/health >/dev/null && { echo "==> Restored and running."; exit 0; }
  sleep 1
done
echo "The API did not come back; see: journalctl -u coinvault -n 50" >&2
exit 1
