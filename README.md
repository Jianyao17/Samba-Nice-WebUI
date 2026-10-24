<div align="center">

# 🗂️ Samba-Nice-WebUI

**A modern, minimal, and lightweight web interface for managing Samba shares on Linux.**

[![CI/CD](https://github.com/Jianyao17/Samba-Nice-WebUI/actions/workflows/ci.yml/badge.svg)](https://github.com/Jianyao17/Samba-Nice-WebUI/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![NiceGUI](https://img.shields.io/badge/NiceGUI-2.x-5898D4)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Samba](https://img.shields.io/badge/Samba-SMB-green)

</div>

---

Samba-Nice-WebUI lets you create, edit, and organize Samba shares from a clean browser UI instead of hand-editing `smb.conf`. It is written in Python with [NiceGUI](https://nicegui.io/) for the interface and [Pydantic](https://docs.pydantic.dev/) for typed configuration, and ships as a single small, non-privileged Docker container.

## ✨ Features

- **Dashboard** – Real-time overview of the Samba service status and the number of active shares.
- **Share Management** – Create, edit, rename, and delete shares, with duplicate-name protection.
- **Directory Picker** – Browse a lazy, expandable folder tree to choose a share path inside your allowed storage roots.
- **Storage Explorer** – Browse and create folders in list or icon view, with one panel per storage root.
- **SMB Access Address** – Every share shows a copyable `smb://` address (and a Windows UNC path when applicable).
- **Safe Config Handling** – All shares live in one dedicated include file, so your main `smb.conf` is never touched. Every change is validated with `testparm` before it is applied.
- **Change History & Undo** – A linear history with field-level diff previews and one-click undo.
- **Zero-Downtime Reload** – Changes are applied by sending `SIGHUP` to `smbd`, so connected clients are not interrupted.
- **Mock Dev Mode** – A fully working UI on Windows/macOS with no Samba installation required.

## 🚀 Installation (Linux + Docker Compose)

**Requirements:** a Linux host with Samba (`smbd`) installed and running, plus Docker with the Compose plugin. No need to clone the repository.

**1. Add the include line (one-time).** Open `/etc/samba/smb.conf` and add this line under `[global]`:

```ini
[global]
   # ... your existing settings ...
   include = /etc/samba/smb.webui.conf
```

The filename can be anything, as long as it matches `SAMBA_INCLUDE_CONF_PATH` below.

**2. Create a `docker-compose.yml`:**

```yaml
services:
  samba-webui:
    image: ghcr.io/jianyao17/samba-nice-webui:latest
    container_name: samba-nice-webui
    restart: unless-stopped
    pid: "host"            # needed to send SIGHUP to the host's smbd
    ports:
      - "8082:8080"
    environment:
      - WEBUI_ADMIN_USER=admin
      - WEBUI_ADMIN_PASSWORD=change-me
      - WEBUI_SECRET_KEY=change-me-to-a-long-random-string
      - ALLOWED_STORAGE_ROOTS=/storage
      - SAMBA_INCLUDE_CONF_PATH=/etc/samba/smb.webui.conf
      - SAMBA_BACKUP_DIR=/etc/samba/.backups
      - SAMBA_PID_FILE=/var/run/samba/smbd.pid
      # - SAMBA_SMB_HOST=nas.local
    volumes:
      - /etc/samba:/etc/samba
      - /var/run/samba:/var/run/samba
      - /srv/samba:/storage   # host folder that holds your shared data
```

**3. Start it:**

```bash
docker compose up -d
```

Open `http://<your-server-ip>:8080` and sign in with the credentials you set.

> **Note:** Change `WEBUI_ADMIN_PASSWORD` and `WEBUI_SECRET_KEY` before exposing the app to a network.

## ⚙️ Environment Variables

Settings are read from environment variables or a `.env` file (see [`.env.example`](.env.example)).

| Variable | Default | Description |
|---|---|---|
| `WEBUI_HOST` | `0.0.0.0` | Interface the WebUI binds to |
| `WEBUI_PORT` | `8080` | WebUI HTTP port |
| `WEBUI_ADMIN_USER` | `admin` | Login username |
| `WEBUI_ADMIN_PASSWORD` | `adminpassword` | Login password. **Change in production** |
| `WEBUI_SECRET_KEY` | *(insecure default)* | Session signing key. **Change in production** |
| `WEBUI_AUTO_RELOAD` | `false` | Auto-reload on code changes (development only) |
| `SAMBA_INCLUDE_CONF_PATH` | `/etc/samba/smb.webui.conf` | The only file this app reads and writes |
| `SAMBA_BACKUP_DIR` | `/etc/samba/.backups` | Where configuration history is stored |
| `SAMBA_PID_FILE` | `/var/run/samba/smbd.pid` | `smbd` PID file used for `SIGHUP` reload |
| `SAMBA_SMB_HOST` | *(empty)* | Hostname/IP shown in SMB addresses. Empty uses the browser's host |
| `SAMBA_SMB_PORT` | `445` | SMB port shown in SMB addresses |
| `SAMBA_BACKEND` | `linux` | `linux` for a real Samba host, `mock` for an in-memory simulation |
| `ALLOWED_STORAGE_ROOTS` | `/storage` | Comma-separated folders the WebUI may browse or create in. Each root gets its own panel |

## 💻 Local Setup

Clone the repository first:

```bash
git clone https://github.com/Jianyao17/Samba-Nice-WebUI.git
cd Samba-Nice-WebUI
```

### Option A: Docker (recommended on Windows)

Starts a real Samba container plus the WebUI, fully isolated from your host. Works with Docker Desktop and needs no `smb.conf` editing.

```bash
docker compose -f docker-compose.test.yml up --build --watch
```

- **WebUI:** http://localhost:8080 (default login: `admin` / `adminpassword`)
- **Samba:** `smb://localhost:1445/<share_name>`

To reset everything, run `docker compose -f docker-compose.test.yml down -v`.

### Option B: Manual with uv (Mock mode)

**Requirements:** [uv](https://docs.astral.sh/uv/) and Python 3.11+. Runs in Mock mode, so no Samba is needed.

```bash
cp .env.example .env        # Windows: copy .env.example .env
uv sync --extra dev
uv run python -m src.main
```

Open http://localhost:8080 and sign in with `admin` / `adminpassword`.

## 🧪 Running Tests

```bash
# Unit and workflow tests (real-Samba tests are skipped automatically)
uv run pytest -v

# Full suite, including integration tests against a real smbd in a container
docker build -f Dockerfile.test -t samba-nice-test .
docker run --rm samba-nice-test
```

## 🛡️ Security Model

- **No Docker socket and no `privileged` mode.** The container runs with default capabilities.
- **No shell injection.** Subprocess calls always use argument lists.
- **Path traversal protection.** Browsing and folder creation are strictly limited to `ALLOWED_STORAGE_ROOTS`.
- **Minimal write scope.** Only the include file and the history directory are ever written.

## 🕘 Configuration History

Each successful save or delete records an entry in `SAMBA_BACKUP_DIR`, named `snapshot_<YYYYMMDD>T<HHMMSS>_<sha256[:8]>`. The History page shows added, removed, and changed shares, and **Undo** restores the configuration from before an entry while removing that entry and every newer one. If the include file is edited manually, a drift warning appears and the next save records it as a checkpoint.

## 📂 Project Structure

```text
src/
├── main.py        # Entry point and routes
├── config.py      # Typed settings (env → Pydantic)
├── core/          # Models, security, SMB address, diff, history manager
├── samba/         # Linux and mock backends, parser, share operations
├── storage/       # Bounded directory manager
└── ui/            # Pages: dashboard, shares, storage, history
tests/             # Unit and integration tests
```

## License
MIT License.