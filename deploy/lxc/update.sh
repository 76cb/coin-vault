#!/usr/bin/env bash
# Update an LXC install of Coin Vault to the latest commit on its branch.
# Take an LXC snapshot first (see README, "Updating").
#
#     /opt/coinvault/app/deploy/lxc/update.sh            # pull, rebuild, migrate, restart
#     /opt/coinvault/app/deploy/lxc/update.sh --no-pull  # rebuild from files already in place
set -euo pipefail

APP_DIR=/opt/coinvault/app
VENV=/opt/coinvault/venv
ENV_FILE=/etc/coinvault/coinvault.env

# Run a command as the coinvault user with the app's environment loaded.
as_app() { sudo -u coinvault bash -c 'set -a; . "$0"; set +a; exec "$@"' "$ENV_FILE" "$@"; }

# Provider API keys are encrypted with this; create it once and never replace it.
ensure_encryption_key() {
  if ! grep -q '^CV_ENCRYPTION_KEY=..*' "$ENV_FILE"; then
    local key
    key="$(openssl rand -base64 32)"
    if grep -q '^CV_ENCRYPTION_KEY=' "$ENV_FILE"; then
      sed -i "s#^CV_ENCRYPTION_KEY=.*#CV_ENCRYPTION_KEY=$key#" "$ENV_FILE"
    else
      printf '\n# Encrypts provider API keys in the database. Keep it with your backups.\nCV_ENCRYPTION_KEY=%s\n' "$key" >> "$ENV_FILE"
    fi
    echo "Added CV_ENCRYPTION_KEY to $ENV_FILE."
  fi
}

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
cd "$APP_DIR"

if [[ "${1:-}" != "--no-pull" ]]; then
  echo "==> Pulling the latest code"
  git fetch --quiet origin
  BEFORE="$(git rev-parse HEAD)"
  git merge --ff-only "@{u}"
  echo "    $BEFORE -> $(git rev-parse HEAD)"
  # Bash keeps running the copy of this script it started with, so hand over to the
  # version just pulled; otherwise new update steps would only run on the next update.
  exec "$APP_DIR/deploy/lxc/update.sh" --no-pull
fi

ensure_encryption_key

# Before 2026-10-31, uploads were saved 0600, which nginx (reading via the coinvault group) can't serve.
chmod -R g+rX /var/lib/coinvault/media

echo "==> Updating the backend"
"$VENV/bin/pip" install -q --upgrade -e "$APP_DIR/backend"

echo "==> Rebuilding the frontend"
(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)

echo "==> Applying migrations"
(cd backend && as_app "$VENV/bin/python" -m app.cli migrate)

install -m 0644 deploy/lxc/coinvault.service /etc/systemd/system/coinvault.service
install -m 0644 deploy/lxc/nginx-coinvault.conf /etc/nginx/sites-available/coinvault
systemctl daemon-reload
nginx -t && systemctl reload nginx
systemctl restart coinvault

for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8000/api/v1/health >/dev/null && { echo "==> Coin Vault is running."; exit 0; }
  sleep 1
done
echo "The API did not come back; see: journalctl -u coinvault -n 50. Roll back with your LXC snapshot if needed." >&2
exit 1
