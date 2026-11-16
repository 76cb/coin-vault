# Install and operations

The [README](../README.md#install) covers the first install: the Proxmox helper script and the steps it automates. This page has the rest: storage, updating, backups and restore, useful commands, and the Ollama server for Photo AI.

## Contents

- [What the installer sets up](#what-the-installer-sets-up)
- [Storage](#storage)
- [Useful commands](#useful-commands)
- [Updating](#updating)
- [Backups and restore](#backups-and-restore)
- [Photo AI: Ollama on the GPU](#photo-ai-ollama-on-the-gpu)

## What the installer sets up

`deploy/lxc/install.sh` targets a Debian 13 LXC. Debian 12 also works, because the installer fetches Python 3.12 and Node 22 itself. It installs PostgreSQL 16, Python, nginx and Node, creates the database with a random password, builds the frontend, and starts the backend as the `coinvault` systemd service behind nginx.

| What | Where |
| --- | --- |
| Application code | `/opt/coinvault/app` |
| Python virtualenv | `/opt/coinvault/venv` |
| Configuration (database password, `CV_ENCRYPTION_KEY`) | `/etc/coinvault/coinvault.env` |
| Photos and documents | `/var/lib/coinvault/media` |
| Backups | `/var/lib/coinvault/backups` (or `CV_BACKUP_DIR`) |
| Service | `coinvault.service` (`deploy/lxc/coinvault.service`) |
| nginx site | `deploy/lxc/nginx-coinvault.conf` |

The helper script `deploy/proxmox/coinvault-lxc.sh` copies your GitHub token and admin password into the container as root-only files; they never appear on a command line or in its output. It also asks whether to keep the token in the container so that `update.sh` can pull updates later.

## Storage

Photos and documents live in `/var/lib/coinvault/media`. To keep them on a separate, larger disk, add a mount point to the container before installing (the helper script offers this as "a separate disk for photos"):

```sh
pct set <vmid> -mp0 <storage>:64,mp=/var/lib/coinvault
```

Replace `<storage>` with a Proxmox storage pool name and `64` with the size in GB.

## Useful commands

Inside the container:

```sh
systemctl status coinvault              # is it running?
journalctl -u coinvault -f              # live logs
cat /etc/coinvault/coinvault.env        # configuration

# reset the admin password
cd /opt/coinvault/app/backend && sudo -u coinvault bash -c 'set -a; . /etc/coinvault/coinvault.env; exec /opt/coinvault/venv/bin/python -m app.cli reset-password --username admin'
```

From the Proxmox host, put `pct exec <vmid> --` in front of any of them.

## Updating

Take a snapshot first, so you can roll back in seconds if an update goes wrong. On the Proxmox host:

```sh
pct snapshot <vmid> before-update-$(date +%Y%m%d)
```

Then inside the container:

```sh
/opt/coinvault/app/deploy/lxc/update.sh
```

It pulls the latest code, backs up (see below), rebuilds, migrates the database and restarts the service. If the backup fails it stops before changing anything (`SKIP_BACKUP=1` skips it). It also adds `CV_ENCRYPTION_KEY` to the env file if it is missing (installs from before Milestone 2).

To roll back, run `pct rollback <vmid> <snapshot-name>` on the host, or restore the pre-update backup.

## Backups and restore

Coin Vault backs itself up every night at 03:15 (change the time, or turn it off, in Settings, Backups). An update backs up first too, and Settings has **Back up now**.

- **What is in a backup:** the whole database at that moment, and every photo, document and display copy. Photos are stored once and shared by all backups, so a nightly backup only adds what is new. Each backup is checked after it is made: the database copy is read back, and every listed file is confirmed present and complete.
- **Where:** `/var/lib/coinvault/backups` (set `CV_BACKUP_DIR` to use another folder, such as a mounted NAS or second disk).
- **How many:** the newest three, one a day for a week, one a week for a month, and one a month for a year. Files no remaining backup lists are removed.
- **Not included, on purpose:** `/etc/coinvault/coinvault.env`, which holds the database password and `CV_ENCRYPTION_KEY`. Keep a copy of it somewhere safe. Without it, a restore still brings back the whole collection; only saved provider API keys need typing in again.
- **Keep one off the server:** the backup folder is on the same disk as the collection. In Settings, **Download** gives any backup as one `.tar` (database and every file) to keep elsewhere.

To restore, inside the container (from the Proxmox host, put `pct exec <vmid> --` in front):

```sh
/opt/coinvault/app/deploy/lxc/restore.sh                       # list the backups
/opt/coinvault/app/deploy/lxc/restore.sh 2026-10-31T071500Z    # put one back
/opt/coinvault/app/deploy/lxc/restore.sh /root/coinvault-backup-2026-10-31T071500Z.tar   # or a downloaded copy
```

It asks before going ahead, backs up the current state first (so a restore can be undone), stops the service, replaces the database, copies back any missing files, brings an older backup's database up to the current version, and starts the service again.

For other installs the same steps are `python -m app.cli backup`, `list-backups` and `restore`. The test suite backs up, damages and restores a collection on SQLite and PostgreSQL, including from a downloaded `.tar`.

## Photo AI: Ollama on the GPU

Photo AI needs an [Ollama](https://ollama.com) server with a vision model. On a Proxmox host with an NVIDIA card, `deploy/proxmox/ollama-lxc.sh` creates one in its own container, so Coin Vault's container stays as it is. The host's NVIDIA driver must already work (`nvidia-smi` shows the card). Run on the Proxmox host:

```sh
pct pull <coinvault-vmid> /opt/coinvault/app/deploy/proxmox/ollama-lxc.sh /root/ollama-lxc.sh
bash /root/ollama-lxc.sh            # --dry-run shows what it would do
```

It creates a Debian container (16 GB RAM, 80 GB disk by default), passes the GPU through (Proxmox VE 8.1 or newer), installs the NVIDIA user-space libraries matching the host driver (no kernel module), installs Ollama listening on port 11434, and downloads `gemma4:26b` (about 17–19 GB, which fits a 24 GB card with room for photos; `--model gemma4:12b` is smaller and quicker). It checks the model runs on the GPU and prints the address.

Then in Coin Vault, Settings, AI: enter `http://<ollama-container-ip>:11434`, press Check the server, choose the model and press Use this model. Only models that can see photos are offered.

- **After updating the host's NVIDIA driver**, match it in the container: `bash /root/ollama-lxc.sh --update-driver <ollama-vmid>`. Until then CUDA fails and Ollama falls back to the CPU (slow).
- **Ollama has no password.** Keep it on your private network, and do not forward port 11434.
- **Another machine:** any Ollama server Coin Vault can reach works; it must listen on the network (`OLLAMA_HOST=0.0.0.0:11434`).
- The first photo after a while takes longer while the model loads into the GPU; it then stays loaded for 30 minutes.
