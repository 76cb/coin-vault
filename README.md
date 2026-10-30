# Coin Vault

A self-hosted app for cataloguing and valuing a personal precious-metals and coin collection. It runs on a Proxmox home server and is used from a browser on your laptop or phone.

> **Private network only.** Coin Vault has a single admin login and plain-http defaults meant for a home LAN. Do not port-forward it or expose it to the internet. If you want remote access, use a VPN (WireGuard, Tailscale) into your network instead.

## Status

| Milestone | Scope | State |
| --- | --- | --- |
| 1 | Sign-in, items, photos, documents, bulk photo upload | Done |
| 2 | Spot prices, melt value, dashboard | Next |
| 3 | Valuation history, exports, backups | Planned |
| 4 | Sold-price comps (SoldComps, Numista, manual), quota manager | Planned |
| 5 | Local AI identification and grading (optional) | Planned |

## What works now

- **Sign-in:** one admin account with argon2id passwords. Server-side sessions use an HttpOnly cookie, and every change needs a CSRF token. Repeated failed logins are throttled.
- **API tokens:** scoped (`items:read`, `items:write`, `prices:read`, `export`), with optional expiry and revocation. They're meant for scripts and other tools on your LAN.
- **Items:** six types (coin, bullion coin or round, bar, banknote, junk/constant-content lot, other), each with its own fields.
  - Condition is raw (Sheldon grade or descriptive) or slabbed (company, grade, cert number, designations such as CAC).
  - Metal content is entered per piece. Pure troy ounces are computed from gross weight × fineness, and you can override them. Bars convert g, ozt, kg and tola.
  - Purchase price is optional: mark a cost as known, estimated or unknown.
  - Each item also has storage location (nested), tags, status and sale details.
- **Edits:** saves are protected against conflicts. If you edit an item in two browser tabs, the second save is refused rather than silently overwriting the first.
- **History:** every change to a value-affecting field is recorded in the item's history: quantity, price, fees, status, sale, grade, metal content and valuation rule.
- **Photos:** several per item, with roles (obverse, reverse, edge, slab front, slab back, other). You can reorder them and choose a cover. On upload:
  - The file type is checked from its content, not its extension, and size is capped.
  - GPS location is removed losslessly from JPEGs. HEIC from phones becomes a high-quality JPEG.
  - Photos are auto-rotated for display and get thumbnails.
  - Each is checked for blur, glare, low resolution and dark exposure, with advice on retaking.
  - Possible duplicates are flagged: an exact match, or a near match by perceptual hash.
- **Bulk upload:** drop a batch from your camera.
  - Files named like `0042_obv.jpg` / `0042_rev.jpg` (also `_o`/`_r`, `-front`/`-back`, `_edge`, `_slab_front`, `_slab_back`) are paired by name. Everything else is paired in upload order.
  - You can split, merge or re-role a group.
  - Then save each group as a new item or add it to an existing one.
- **Documents:** receipts, invoices, certificates and assay cards (PDF or image), linked to one or more items. They're served only to the signed-in owner.
- **Operations:** migrations run on startup, and there's a health endpoint (`/api/v1/health`, plus `/api/v1/health/ready` when signed in). Logs are structured JSON with secrets redacted.

The interactive API reference is at `http://<host>/api/v1/docs`.

## Install on Proxmox (native LXC)

These steps target a **Debian 13** LXC; Debian 12 also works (the script fetches Python 3.12 and Node 22 itself).

1. In Proxmox, create an unprivileged container from the Debian 13 template. A good start is 2 cores, 2 GB RAM and a 16 GB root disk. Photos grow over time; see **Storage** below.
2. Open the container's console and install git:
   ```sh
   apt update && apt install -y git
   ```
3. Clone the repository. It is private, so use a GitHub personal access token with read access to this repo:
   ```sh
   git clone https://<your-token>@github.com/76cb/coin-vault.git /root/coin-vault
   ```
4. Run the installer:
   ```sh
   cd /root/coin-vault && ./deploy/lxc/install.sh
   ```
   It installs PostgreSQL 16, Python, nginx and Node, then creates the database with a random password in `/etc/coinvault/coinvault.env`. It builds the app, starts it as the `coinvault` systemd service, and asks you for the admin username and password.
5. Open `http://<container-ip>/` from a browser on your LAN.

**Storage.** Photos and documents live in `/var/lib/coinvault/media`. To keep them on a separate, larger disk, add a mount point to the container before installing:
```sh
pct set <vmid> -mp0 <storage>:64,mp=/var/lib/coinvault
```
Replace `<storage>` with a Proxmox storage pool name.

**Useful commands inside the container:**
```sh
systemctl status coinvault              # is it running?
journalctl -u coinvault -f              # live logs
cat /etc/coinvault/coinvault.env        # configuration
cd /opt/coinvault/app/backend && sudo -u coinvault bash -c 'set -a; . /etc/coinvault/coinvault.env; exec /opt/coinvault/venv/bin/python -m app.cli reset-password --username admin'
```

### Updating

Take a snapshot first, so you can roll back in seconds if an update goes wrong. Run this on the Proxmox host:
```sh
pct snapshot <vmid> before-update-$(date +%Y%m%d)
```
Then inside the container:
```sh
/opt/coinvault/app/deploy/lxc/update.sh
```
It pulls the latest code, rebuilds, migrates the database and restarts the service. To roll back, run `pct rollback <vmid> <snapshot-name>` on the host.

Docker Compose, the GPU container for the AI service, encrypted backups and a Caddy HTTPS example arrive in later milestones.

## Configuration

All settings are environment variables prefixed `CV_`; see [`.env.example`](.env.example). The ones you're most likely to change:

| Variable | Default | Meaning |
| --- | --- | --- |
| `CV_DATABASE_URL` | SQLite file | PostgreSQL URL in production |
| `CV_MEDIA_ROOT` | `./media` | Where photos and documents are stored |
| `CV_COOKIE_SECURE` | `false` | Set `true` only when served over HTTPS |
| `CV_MAX_PHOTO_MB` / `CV_MAX_DOCUMENT_MB` | 40 / 25 | Upload size limits |
| `CV_MAX_FILES_PER_UPLOAD` | 200 | Files per bulk upload |
| `CV_USE_X_ACCEL` | `false` | `true` when nginx serves protected files (the LXC install sets this) |

## Development

Requirements: Python 3.12+, Node 20.19+, and optionally PostgreSQL 16.

```sh
# Backend (SQLite by default)
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m app.cli create-admin --username admin
uvicorn app.main:app --reload            # http://127.0.0.1:8000

# Frontend (proxies /api to the backend)
cd frontend
npm ci
npm run dev                              # http://localhost:5173
```

### Tests

```sh
cd backend && pytest                                         # 45 API and unit tests on SQLite
CV_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db pytest   # same tests on PostgreSQL (wipes that db)

cd frontend && npx playwright install chromium && npx playwright test
# Playwright builds the frontend and starts a throwaway server. It runs the
# add-item-with-photos and bulk-upload flows at desktop and phone sizes.
# Set PW_CHROME_PATH to use an installed Chrome instead of downloading one.
```

GitHub Actions runs all of these on every push.

## Using the API with a token

Create a token in **Settings → API tokens**, then:
```sh
curl -H "Authorization: Bearer cv_xxxxxxxxxx_..." http://<host>/api/v1/items?type=coin
```
Tokens can do only what their scopes allow. Writes with a token don't need the CSRF header; browser sessions do.

## Known limits (Milestone 1)

- **Untuned photo-quality thresholds.** The blur, glare and resolution limits are generic starting values and haven't been tuned against your USB camera yet. Expect to adjust them once you've uploaded real photos.
- **Resolution check uses the whole photo.** It looks at the photo's shorter side, not the coin's diameter, because auto-cropping to the coin isn't implemented yet.
- **Discarded uploads keep their files.** A discarded group stays on disk so nothing you photographed is lost. There's no "empty the bin" action for them yet.
- **Login throttling resets on restart.** The failed-login counter is kept in memory, which suits the single-process service.
- **Sold-price data isn't available yet.** Melt values, spot prices, market values, exports and backups come in Milestones 2 and 3.
