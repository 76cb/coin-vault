# Coin Vault

A self-hosted app for cataloguing and valuing a personal precious-metals and coin collection. It runs on a Proxmox home server and is used from a browser on your laptop or phone.

> **Private network only.** Coin Vault has a single admin login and plain-http defaults meant for a home LAN. Do not port-forward it or expose it to the internet. If you want remote access, use a VPN (WireGuard, Tailscale) into your network instead.

## Status

| Milestone | Scope | State |
| --- | --- | --- |
| 1 | Sign-in, items, photos, documents, bulk photo upload | Done |
| 2 | Spot prices, melt value, dashboard | Done |
| 3 | Valuation history, exports, backups | Next |
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
- **Spot prices:** gold, silver, platinum and palladium are fetched every 15 minutes (configurable) from [gold-api.com](https://gold-api.com), which needs no key.
  - gold-api.com's platinum and palladium had stopped updating when checked (Sep 17 and Oct 16, 2026), so every price is judged by its own timestamp. Out-of-date metals come from [Metal Sentinel](https://metal-sentinel.com) (free RapidAPI key, 7,500 requests a month), then [Metals.Dev](https://metals.dev) (free key, 100 a month).
  - Backups are asked only for the metals still missing, and their calls are paced so the free allowance lasts the month.
  - Polling pauses while the metals markets are closed (Friday 5 pm to Sunday 6 pm New York time), and a price older than the stale threshold is marked stale.
  - A price is stored only if it parses as a positive number; a failed or malformed answer moves on to the next provider and is logged.
  - The header shows the latest prices and when they were fetched.
- **Melt value:** quantity × pure ounces × spot, per metal. Items without metal content have no melt value rather than zero.
  - 36 reference compositions are built in: US 90%, 40% and 35% silver, pre-1933 US gold, and common bullion (Eagles, Maple Leafs, Krugerrands, Britannias, Philharmonics, Pandas and others). You can add your own.
  - The item form suggests a composition from country, denomination, year, mint mark and title. When the details fit more than one (an 1881 dollar could be silver or gold), it lists them all.
  - Junk silver and gold lots are valued by face value × the composition's pure ounces per $1, including a worn-90% figure.
  - Each item has a valuation rule: the higher of melt and market (the default), melt, market or what you paid.
- **Market values:** on an item, under Market value:
  - **Search sold listings** searches recent eBay sales through your SoldComps key (one request per search), shows each sale with photo, date and price, and saves the median of the ones you tick, with or without shipping.
  - **Enter a value** records a dealer quote, price guide or appraisal with its date and source.
  - The newest value by date is used; older ones stay in the item's list.
- **Dashboard:** total melt value, what you paid (known and estimated, with a count of items with no cost), gain on items that have both, and pure ounces by metal.
  - A chart of the spot price, or of what your holdings would have been worth, over a day to a year.
  - Breakdowns by metal, type and storage location.
- **Data providers (Settings):** each provider has a key field, a test button, an on/off switch and a monthly request cap.
  - Keys are encrypted (AES-GCM) before they're stored and are never returned by the API; only the last four characters are shown.
  - Usage is counted on every call and, where the provider reports it, synced from the provider's own figures daily and when you press Test. The provider's count wins.
  - The usage meter turns amber at 80% of the cap and red at the cap, where calls stop until the period resets. Daily counts and the last calls are listed.
  - SoldComps usage is read from its headers after every search and from its free usage endpoint daily and on Test.
- **Operations:** migrations run on startup, and there's a health endpoint (`/api/v1/health`, plus `/api/v1/health/ready` when signed in). Logs are structured JSON with secrets redacted.

The interactive API reference is at `http://<host>/api/v1/docs`.

## Install on Proxmox: helper script (recommended)

Run this in the **Proxmox host's** shell (Datacenter → your node → Shell). It creates a Debian 13 container and installs everything into it.

1. Get the script onto the host. The repo is private, so you need a GitHub token: a fine-grained token with access to this repo and *Contents: Read-only*. Run these one block at a time.

   Enter the token. Paste only the token, then press Enter; nothing shows while you paste.
   ```sh
   read -rsp "GitHub token: " GITHUB_TOKEN; export GITHUB_TOKEN; echo
   ```
   Check it works. This should print `200`.
   ```sh
   curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/repos/76cb/coin-vault
   ```
   If it prints `401`, the token is wrong or empty. If it prints `404`, the token doesn't include this repo.

   Download the script:
   ```sh
   curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github.raw" \
     https://api.github.com/repos/76cb/coin-vault/contents/deploy/proxmox/coinvault-lxc.sh -o coinvault-lxc.sh
   ```
2. Run it and answer the questions. Press Enter to accept each default.
   ```sh
   bash coinvault-lxc.sh
   ```
   It asks for:
   - the container ID, hostname, CPU cores, RAM, disk and storage pool;
   - an optional separate disk for photos;
   - the network bridge and address (DHCP or static);
   - the admin username and password.

   It also asks whether to keep the token in the container so that `update.sh` can pull updates later.
3. When it finishes, it prints the address to open, such as `http://192.168.1.50/`.

Options:
- `bash coinvault-lxc.sh --dry-run` shows every command without changing anything.
- `--yes` accepts all the defaults and prints a generated admin password at the end.
- `--help` lists the flags, for example `--ctid 120 --storage fast-ssd --ip 192.168.1.50/24 --media-disk 64`.

Your token and admin password are copied into the container as root-only files. They never appear on a command line or in the output.

## Install on Proxmox: by hand (native LXC)

The steps the helper script automates, if you'd rather do them yourself. These target a **Debian 13** LXC. Debian 12 also works, because the installer fetches Python 3.12 and Node 22 itself.

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
It pulls the latest code, rebuilds, migrates the database and restarts the service. It also adds `CV_ENCRYPTION_KEY` to the env file if it's missing (installs from before Milestone 2). To roll back, run `pct rollback <vmid> <snapshot-name>` on the host.

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
| `CV_ENCRYPTION_KEY` | none | Encrypts provider API keys; the installer and updater generate it |
| `CV_SCHEDULER_ENABLED` | `true` | Background price polling and the daily usage sync |
| `CV_TIMEZONE` | `America/New_York` | Timezone for market hours |

**Back up `CV_ENCRYPTION_KEY`** along with the database (it's in `/etc/coinvault/coinvault.env`). Without it, saved API keys can't be decrypted and you'd have to enter them again; nothing else is lost.

Poll interval, stale threshold, weekend pause and currency are set in **Settings → Spot prices**.

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
cd backend && pytest                                         # 75 API and unit tests on SQLite
CV_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db pytest   # same tests on PostgreSQL (wipes that db)

cd frontend && npx playwright install chromium && npx playwright test
# Playwright builds the frontend and starts a throwaway server. It runs the
# add-item, bulk-upload, composition, dashboard and provider-key flows at
# desktop and phone sizes. Provider calls are mocked in the backend tests and
# the e2e server doesn't poll, so no test reaches the internet.
# Set PW_CHROME_PATH to use an installed Chrome instead of downloading one.
```

GitHub Actions runs all of these on every push.

## Using the API with a token

Create a token in **Settings → API tokens**, then:
```sh
curl -H "Authorization: Bearer cv_xxxxxxxxxx_..." http://<host>/api/v1/items?type=coin
```
Tokens can do only what their scopes allow. Writes with a token don't need the CSRF header; browser sessions do.

## Known limits

- **Untuned photo-quality thresholds.** The blur, glare and resolution limits are generic starting values and haven't been tuned against your USB camera yet. Expect to adjust them once you've uploaded real photos.
- **Resolution check uses the whole photo.** It looks at the photo's shorter side, not the coin's diameter, because auto-cropping to the coin isn't implemented yet.
- **Discarded uploads keep their files.** A discarded group stays on disk so nothing you photographed is lost. There's no "empty the bin" action for them yet.
- **Login throttling resets on restart.** The failed-login counter is kept in memory, which suits the single-process service.
- **Market values aren't refreshed automatically.** They're fetched or entered when you choose to, and dated so you can see their age. Exports, valuation history and backups come in Milestone 3.
- **Sold listings in another currency are left out**, not converted.
- **Purchase prices aren't converted between currencies.** Changing the display currency changes spot prices and melt values, not what you paid.
- **The holdings chart uses today's holdings.** It shows what your current metal would have been worth at past prices, not what you held on each date. Valuation history arrives in Milestone 3.
- **Price history starts when you install.** The free spot sources give current prices only, so the chart fills in as the app polls.
