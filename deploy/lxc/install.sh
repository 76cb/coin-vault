#!/usr/bin/env bash
# Install Coin Vault natively in a Debian 12 or 13 LXC (PostgreSQL 16, Python venv, nginx, systemd).
#
# Run as root from a checkout of the repository:
#     git clone https://github.com/76cb/coin-vault.git && cd coin-vault
#     ./deploy/lxc/install.sh
#
# Safe to re-run: existing database, passwords and media are kept.
set -euo pipefail

APP_ROOT=/opt/coinvault
APP_DIR=$APP_ROOT/app
VENV=$APP_ROOT/venv
DATA_DIR=/var/lib/coinvault
ENV_DIR=/etc/coinvault
ENV_FILE=$ENV_DIR/coinvault.env

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
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NODE_MAJOR=22

# Fresh Debian LXC templates often have no generated locale. C.UTF-8 always exists, and
# PostgreSQL must see a UTF-8 locale or it creates SQL_ASCII databases the app cannot use.
export LANG=C.UTF-8 LC_ALL=C.UTF-8 LANGUAGE=

say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mError: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root"
. /etc/os-release
[[ "$ID" == "debian" ]] || die "this script targets Debian 12 or 13 (found $PRETTY_NAME)"

say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends \
  ca-certificates curl gnupg git nginx rsync sudo openssl python3 python3-venv python3-dev build-essential \
  libheif1 postgresql-common

# PostgreSQL 16 from the PostgreSQL project's repository (Debian ships 15 or 17).
if ! dpkg -s postgresql-16 >/dev/null 2>&1; then
  say "Adding the PostgreSQL apt repository and installing PostgreSQL 16"
  /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
  apt-get install -y -q postgresql-16
fi

# Python 3.12 or newer. Debian 13 ships 3.13; on Debian 12 (3.11) use uv to fetch 3.12.
PY=python3
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  say "System Python is older than 3.12; installing Python 3.12 with uv"
  if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  fi
  UV_PYTHON_INSTALL_DIR=$APP_ROOT/python uv python install 3.12
  PY="$(UV_PYTHON_INSTALL_DIR=$APP_ROOT/python uv python find 3.12)"
fi

# Node.js for building the frontend (Vite needs Node 20.19+).
if ! command -v node >/dev/null || [[ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]]; then
  say "Installing Node.js $NODE_MAJOR"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
  apt-get update -q && apt-get install -y -q nodejs
fi

say "Creating the coinvault user and folders"
id coinvault >/dev/null 2>&1 || useradd --system --home-dir $APP_ROOT --shell /usr/sbin/nologin coinvault
install -d -o coinvault -g coinvault -m 0750 "$DATA_DIR" "$DATA_DIR/media" "$DATA_DIR/backups"
install -d -o root -g coinvault -m 0750 "$ENV_DIR"
install -d -m 0755 "$APP_ROOT"

if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  say "Copying the application to $APP_DIR"
  rsync -a --delete --exclude .venv --exclude node_modules --exclude 'frontend/dist' --exclude '*.db' --exclude media \
    "$SRC_DIR/" "$APP_DIR/"
fi
chown -R root:root "$APP_DIR"

say "Setting up the database"
systemctl enable --now postgresql >/dev/null
if [[ ! -f "$ENV_FILE" ]]; then
  DB_PASS="$(openssl rand -hex 24)"
  sudo -u postgres psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'coinvault') THEN
    CREATE ROLE coinvault LOGIN PASSWORD '$DB_PASS';
  ELSE
    ALTER ROLE coinvault PASSWORD '$DB_PASS';
  END IF;
END \$\$;
SQL
  sed -e "s#^CV_DATABASE_URL=.*#CV_DATABASE_URL=postgresql+psycopg://coinvault:$DB_PASS@127.0.0.1:5432/coinvault#" \
      -e "s#^CV_MEDIA_ROOT=.*#CV_MEDIA_ROOT=$DATA_DIR/media#" \
      -e "s#^CV_USE_X_ACCEL=.*#CV_USE_X_ACCEL=true#" \
      "$APP_DIR/.env.example" > "$ENV_FILE"
  chown root:coinvault "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  echo "Wrote $ENV_FILE (database password generated)."
else
  echo "Keeping existing $ENV_FILE."
fi
ensure_encryption_key

# The app's database must be UTF-8, whatever the cluster default is.
DB_ENCODING=$(sudo -u postgres psql -tAc "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='coinvault'")
if [[ -n "$DB_ENCODING" && "$DB_ENCODING" != "UTF8" ]]; then
  TABLES=$(sudo -u postgres psql -d coinvault -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
  if [[ "$TABLES" == "0" ]]; then
    echo "Recreating the empty coinvault database as UTF-8 (it was $DB_ENCODING)."
    sudo -u postgres dropdb coinvault
    DB_ENCODING=""
  else
    die "database 'coinvault' uses $DB_ENCODING and already has tables; back it up and convert it to UTF-8 first"
  fi
fi
if [[ -z "$DB_ENCODING" ]]; then
  sudo -u postgres createdb -O coinvault -E UTF8 -T template0 --locale=C.UTF-8 coinvault
fi

say "Installing the backend into $VENV"
[[ -x "$VENV/bin/python" ]] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$APP_DIR/backend"  # editable: migrations live beside the code

say "Building the frontend"
(cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)

say "Applying database migrations"
(cd "$APP_DIR/backend" && as_app "$VENV/bin/python" -m app.cli migrate)

say "Configuring systemd and nginx"
install -m 0644 "$APP_DIR/deploy/lxc/coinvault.service" /etc/systemd/system/coinvault.service
install -m 0644 "$APP_DIR/deploy/lxc/nginx-coinvault.conf" /etc/nginx/sites-available/coinvault
ln -sf /etc/nginx/sites-available/coinvault /etc/nginx/sites-enabled/coinvault
rm -f /etc/nginx/sites-enabled/default
# nginx (www-data) must read the frontend and, via X-Accel, the media folder.
usermod -aG coinvault www-data
chmod 0750 "$DATA_DIR" "$DATA_DIR/media"
chmod -R g+rX "$DATA_DIR/media"
nginx -t
systemctl daemon-reload
systemctl enable --now coinvault
systemctl reload nginx

for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8000/api/v1/health >/dev/null && break
  sleep 1
done
curl -fs http://127.0.0.1:8000/api/v1/health >/dev/null || die "the API did not start; see: journalctl -u coinvault -n 50"

if ! sudo -u postgres psql -d coinvault -tAc "SELECT 1 FROM users LIMIT 1" | grep -q 1; then
  say "Create the admin account"
  # Unattended installs (the Proxmox helper) pass CV_ADMIN_USER and a root-only CV_ADMIN_PASSWORD_FILE.
  if [[ -n "${CV_ADMIN_USER:-}" && -f "${CV_ADMIN_PASSWORD_FILE:-}" ]]; then
    (cd "$APP_DIR/backend" && as_app "$VENV/bin/python" -m app.cli create-admin --username "$CV_ADMIN_USER" --password-stdin) \
      < "$CV_ADMIN_PASSWORD_FILE"
    shred -u "$CV_ADMIN_PASSWORD_FILE" 2>/dev/null || rm -f "$CV_ADMIN_PASSWORD_FILE"
  else
    read -rp "Admin username [admin]: " ADMIN_USER
    ADMIN_USER=${ADMIN_USER:-admin}
    (cd "$APP_DIR/backend" && as_app "$VENV/bin/python" -m app.cli create-admin --username "$ADMIN_USER")
  fi
fi

IP="$(hostname -I | awk '{print $1}')"
say "Done. Open http://$IP/ on your LAN."
echo "Keep this container off the internet: Coin Vault is built for a private network only."
