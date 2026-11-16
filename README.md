<h1 align="center">Coin Vault</h1>

<p align="center">
  Self-hosted inventory and valuation for a personal coin and precious-metals collection.<br>
  Runs in a container on a home server; used from a browser on a laptop or phone.
</p>

<p align="center">
  <a href="https://github.com/76cb/coin-vault/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/76cb/coin-vault/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-backend-009688">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61DAFB">
  <img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-4169E1">
</p>

<p align="center">
  <img src="docs/screenshots/collection.jpg" alt="The collection page: a grid of coin and bar tiles with their current value and what was paid" width="900">
</p>

> **Private network only.** Coin Vault has a single admin login and plain-http defaults meant for a home LAN. Do not port-forward it or expose it to the internet. For remote access, use a VPN (WireGuard, Tailscale) into your network.

The screenshots in this file come from a demo collection. The coin pictures in them are drawn placeholders, not photographs of real coins.

## Contents

- [What it does](#what-it-does)
- [A tour](#a-tour)
- [Install](#install)
- [Configuration](#configuration)
- [Development](#development)
- [Using the API with a token](#using-the-api-with-a-token)
- [Project layout](#project-layout)
- [Known limits](#known-limits)
- [Further reading](#further-reading)

## What it does

**Catalogue.** Coins, bullion coins and rounds, mint and proof sets, bars, banknotes, Goldbacks, junk-silver lots and anything else, each with its own fields, grade or slab details, purchase record, storage location (nested), tags and status. Paste a listing title such as `2021 $1 Silver Eagle T2 First Production PCGS MS70` and the form fills itself in, metal content included. A PCGS cert number, a PCGS number and grade, or a slab's barcode does the same.

**Photos.** Several per item with roles (obverse, reverse, edge, slab front and back). Bulk upload pairs files by name (`0042_obv.jpg` / `0042_rev.jpg`), checks each for blur, glare and low resolution, strips GPS data, converts HEIC and flags duplicates. A non-destructive editor crops, straightens, cuts the coin out on a clear background and squares up a slab photographed at an angle.

**Value.** Spot prices for gold, silver, platinum and palladium are fetched every 15 minutes from free sources, with a fallback chain when one goes stale. Melt value comes from each piece's pure metal, taken from about 700 built-in reference compositions (US silver and gold, world coins by weight standard, bullion lines, refiners' bars) that cite their sources. Market values come from sold listings, the PCGS price guide, Numista estimates, or figures you enter, and are refreshed weekly. The dashboard shows what the collection is worth today and what it was worth on any day since you installed.

**Keep it safe.** Nightly backups of the database and every photo, verified after they are made, with a one-command restore. Exports as CSV and a printable insurance report. Read-only logins for a spouse, heir or insurer. Scoped API tokens for scripts on your LAN.

**Photo AI (optional).** A vision model on your own network, through Ollama, reads a coin's date, mint mark and design from its photos, reads slab labels, and suggests a grade range for raw coins. Photos never leave your network.

The full list, feature by feature, is in [docs/features.md](docs/features.md).

## A tour

### Dashboard

Total value, what you paid, gain, pure ounces by metal with your average cost per ounce next to spot, the collection's value over time against what you had paid, and breakdowns by metal, type and location.

<p align="center"><img src="docs/screenshots/dashboard.png" alt="Dashboard with collection value, melt, market, paid and gain figures, ounces by metal and a value-over-time chart" width="900"></p>

### An item

Current value and how it was arrived at, every detail, metal content, purchase record, market values with their sources, photos with their quality checks, documents and a history of every value-affecting change.

<p align="center"><img src="docs/screenshots/item.jpg" alt="An item page for a slabbed Morgan dollar: value, details, metal content, purchase and market value" width="900"></p>

### Adding an item

Paste a listing title and the form fills in type, year, product or series, grading company, grade, designations, quantity and the matching reference composition. Check it, add the price, save.

<p align="center"><img src="docs/screenshots/add-item.png" alt="The quick add box reading a listing title and filling in the form" width="900"></p>

### Bulk upload

Drop a batch from the camera. Files are paired into obverse and reverse by name or upload order; each group becomes a new item or joins one you already have. Possible duplicates of photos you already hold are pointed out.

<p align="center"><img src="docs/screenshots/upload.png" alt="The upload page with paired photo groups waiting to be saved as items" width="900"></p>

### Photo editor

Crop, turn, mirror and straighten; adjust brightness, contrast, saturation, warmth and sharpness. The circle shape cuts the coin out of its background. Find the coin fits the circle to the rim; Find the slab squares up a holder shot at an angle. The original file is never changed.

<p align="center"><img src="docs/screenshots/photo-editor.jpg" alt="The photo editor with the circle crop fitted to a coin" width="900"></p>

### Photo library

Every photo you have uploaded, once, whether or not it is on an item. Put any of them on any item, or pick a few and create an item from them.

<p align="center"><img src="docs/screenshots/photos.jpg" alt="The photo library showing every uploaded photo" width="900"></p>

### Tools

Series checklists (State Quarters, Presidential dollars, Morgan and Peace dollars, Silver Eagles and more), a want list, sales and gains by year, price alerts, inventory checks, printable storage labels with QR codes, and a CSV importer.

<p align="center"><img src="docs/screenshots/tools.png" alt="The tools page" width="900"></p>
<p align="center"><img src="docs/screenshots/checklists.png" alt="Series checklists showing how many of each design and mint are held" width="900"></p>

### Goldbacks

Pick the series, enter how many of each denomination you hold, and the gold content and melt value follow the gold price.

<p align="center"><img src="docs/screenshots/goldbacks.png" alt="The Goldbacks page" width="900"></p>

### Insurance report

A printable inventory of what you hold: total value, value by location, the spot prices used, and each item with its photos, grade, cert numbers, metal content and value. Print it or save it as a PDF.

<p align="center"><img src="docs/screenshots/report.png" alt="The insurance report" width="900"></p>

### Settings

Appearance, spot-price polling, storage locations, data providers with encrypted keys and monthly caps, backups, weekly value updates, Photo AI, API tokens and read-only logins.

<p align="center"><img src="docs/screenshots/settings.png" alt="The settings page" width="900"></p>

### Dark mode and phones

Follows the device by default; the moon and sun button in the header switches it. Every page works at phone width, and the camera opens from any photo drop zone.

<p align="center"><img src="docs/screenshots/collection-dark.jpg" alt="The collection page in dark mode" width="900"></p>
<p align="center"><img src="docs/screenshots/phone.jpg" alt="The collection, an item and the dashboard on a phone" width="900"></p>

## Install

Coin Vault is built to run in a Debian 13 LXC container on Proxmox: PostgreSQL 16, the FastAPI backend as a systemd service, and nginx in front serving the built frontend and protected media. Debian 12 also works.

### Proxmox helper script (recommended)

Run this in the Proxmox host's shell (Datacenter, your node, Shell). It creates the container and installs everything into it.

The repository is private, so you need a fine-grained GitHub token with access to this repo and *Contents: Read-only*.

```sh
# 1. Enter the token (nothing shows while you paste), then check it: this should print 200
read -rsp "GitHub token: " GITHUB_TOKEN; export GITHUB_TOKEN; echo
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/repos/76cb/coin-vault

# 2. Download the script
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github.raw" \
  https://api.github.com/repos/76cb/coin-vault/contents/deploy/proxmox/coinvault-lxc.sh -o coinvault-lxc.sh

# 3. Run it and answer the questions; Enter accepts each default
bash coinvault-lxc.sh
```

It asks for the container ID, hostname, cores, RAM, disk and storage pool; an optional separate disk for photos; the network bridge and address; and the admin username and password. When it finishes it prints the address to open, such as `http://192.168.1.50/`.

`--dry-run` shows every command without changing anything, `--yes` accepts all the defaults, and `--help` lists the flags (`--ctid 120 --storage fast-ssd --ip 192.168.1.50/24 --media-disk 64`).

### By hand

The steps the script automates:

```sh
# inside a fresh Debian 13 unprivileged container (2 cores, 2 GB RAM, 16 GB disk is a good start)
apt update && apt install -y git
git clone https://<your-token>@github.com/76cb/coin-vault.git /root/coin-vault
cd /root/coin-vault && ./deploy/lxc/install.sh
```

The installer sets up PostgreSQL, Python, nginx and Node, creates the database with a random password in `/etc/coinvault/coinvault.env`, builds the app, starts the `coinvault` service and asks for the admin username and password. Then open `http://<container-ip>/`.

Updating, backups and restore, keeping photos on a separate disk, and setting up Ollama on a GPU for Photo AI are covered in [docs/install.md](docs/install.md).

## Configuration

All settings are environment variables prefixed `CV_`; see [`.env.example`](.env.example). The ones most likely to change:

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
| `CV_TIMEZONE` | `America/New_York` | Timezone for market hours and the nightly backup |
| `CV_BACKUP_DIR` | `backups` next to the media folder | Where backups are kept |
| `CV_PG_BIN` | from `PATH` | Folder with `pg_dump` and `pg_restore` matching the PostgreSQL server |

**Keep a copy of `CV_ENCRYPTION_KEY`.** It lives in `/etc/coinvault/coinvault.env`, which backups leave out on purpose. Without it, saved provider API keys cannot be decrypted and must be entered again; nothing else is lost.

Poll interval, stale threshold, weekend pause and currency are set in Settings, Spot prices.

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

The interactive API reference is at `/api/v1/docs`.

### Tests

```sh
cd backend && pytest                                                  # API and unit tests on SQLite
CV_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db pytest    # the same tests on PostgreSQL (wipes that db)

cd frontend && npx playwright install chromium && npx playwright test
```

Playwright builds the frontend, starts a throwaway server and runs the add-item, bulk-upload, photo-editor, photo-library, values, exports, backups, Goldbacks, mint-set, tools and AI flows at desktop and phone sizes. Provider calls are mocked and the test server does not poll, so no test reaches the internet. Set `PW_CHROME_PATH` to use an installed Chrome instead of downloading one.

GitHub Actions runs the backend tests on SQLite and PostgreSQL 16, the frontend typecheck and the end-to-end tests on every push.

## Using the API with a token

Create a token in Settings, API tokens, then:

```sh
curl -H "Authorization: Bearer cv_xxxxxxxxxx_..." http://<host>/api/v1/items?type=coin
```

Tokens have scopes (`items:read`, `items:write`, `prices:read`, `export`), optional expiry, and can be revoked. Writes with a token do not need the CSRF header; browser sessions do.

## Project layout

```
backend/
  app/
    routers/        HTTP endpoints, one file per area (items, photos, uploads, prices, pcgs, numista, ai, ...)
    services/       the work behind them: valuation, spot prices, images, photo edits, slabs, backups, mint sets
    providers/      spot-price, sold-listing, PCGS and Numista clients
    data/catalogue/ world coin and bullion compositions, one JSON file per region, each row with its source
    models.py       SQLAlchemy models; migrations in alembic/
    cli.py          create-admin, reset-password, migrate, backup, list-backups, restore
  tests/
frontend/
  src/pages/        Collection, Dashboard, ItemPage, NewItem, Upload, Photos, Goldbacks, Tools, Settings, Report
  src/components/   ItemForm, PhotoManager, PhotoEditor, MarketValue, Providers, Backups, ...
  e2e/              Playwright tests and fixtures
deploy/
  proxmox/          coinvault-lxc.sh (create and install a container), ollama-lxc.sh (a GPU container for Photo AI)
  lxc/              install.sh, update.sh, restore.sh, the systemd unit and nginx config
docs/               feature reference, install and operations guide, screenshots
```

## Known limits

- **Untuned photo-quality thresholds.** The blur, glare and resolution limits are generic starting values and have not been tuned against a particular camera. Expect to adjust them once real photos are in.
- **Resolution check uses the whole photo.** It looks at the photo's shorter side, not the coin's diameter, because the coin's size is only found when you use Find the coin in the editor.
- **Discarded uploads keep their files.** A discarded group stays on disk so nothing photographed is lost. There is no "empty the bin" action for them yet.
- **Login throttling resets on restart.** The failed-login counter is kept in memory, which suits the single-process service.
- **Only PCGS and Numista values are refreshed automatically.** Sold-listing medians and your own figures stay as fetched or entered, dated so their age is visible; search sold listings again when you want a newer one.
- **Photo AI can be wrong.** It can misread a worn date or a small mint mark, and a grade from photos is a rough guide: lighting hides wear, cleaning and hairlines. Its answers only fill the form; nothing is saved until you check and save. It does not find die varieties or errors.
- **Sold listings in another currency are left out**, not converted.
- **Purchase prices are not converted between currencies.** Changing the display currency changes spot prices and melt values, not what you paid.
- **Value and price history start when you install.** The free spot sources give current prices only, so the charts fill in as the app polls. Items with no acquired date count from the day they were added.
- **Docker Compose and an HTTPS example** are not provided yet; the supported deployment is the LXC install above.

## Further reading

- [docs/features.md](docs/features.md): everything the app does, area by area, including the title reader, reference compositions and world catalogue, market-value sources, the photo editor, Photo AI, Goldbacks, the tools page and exports.
- [docs/install.md](docs/install.md): updating, backups and restore, storage, useful commands, and Ollama on a GPU.
