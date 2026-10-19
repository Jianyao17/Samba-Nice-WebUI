<div align="center">

# 🗂️ Samba-Nice-WebUI

**A modern, secure, and lightweight web management interface for Samba on Linux.**

Built with Python · [NiceGUI](https://nicegui.io/) · Deployed as a single non-privileged Docker container.

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| **Dashboard** | Real-time overview of Samba service status and active share count |
| **Share Management** | Full CRUD for share configurations (create, edit, delete) |
| **Single Include File** | All managed shares live in one dedicated file — the primary `smb.conf` is never touched |
| **Config Validation** | Every change is validated with `testparm` before being applied |
| **Auto Backup & Rollback** | Timestamped snapshots created before every modification, single-click rollback |
| **Zero-Downtime Reload** | Sends `SIGHUP` to the `smbd` master process via shared PID namespace — no Docker socket, no privileged mode |
| **Storage Safety** | Directory browsing and creation is strictly bounded to configured storage roots |
| **Mock Dev Mode** | Fully functional UI on Windows/macOS without any Samba or Docker installation |

---

## 🏗️ Architecture

```
  Browser
    │
    ▼
┌─────────────────────────────────────────────┐
│     Samba-Nice-WebUI  (Docker container)    │
│                                             │
│  NiceGUI UI ──► SambaBackend               │
│                    │                        │
│                    ├── Reads/Writes ──────► /etc/samba/smb.webui.conf  (include file)
│                    ├── Validates via ──────► testparm
│                    └── Reloads via ───────► SIGHUP → smbd PID
└─────────────────────────────────────────────┘
                         │  (shared volume mounts)
                         ▼
             Linux Host / Samba Container
             /etc/samba/smb.conf   ← untouched
                  └── include = /etc/samba/smb.webui.conf  ← managed here
```

**Key design principle:** This app manages exactly **one file** — the dedicated include file
(`smb.webui.conf`). The primary `smb.conf` with its `[global]` settings is entirely out of scope
and never read or modified.

---

## ⚠️ One-Time Host Prerequisite

Before starting this app in **production** (`SAMBA_BACKEND=linux`), you must add a single
`include` directive to your primary `/etc/samba/smb.conf`:

```ini
[global]
   workgroup = WORKGROUP
   # ... your existing global settings ...

   # Add this line — point it at the path set in SAMBA_INCLUDE_CONF_PATH
   include = /etc/samba/smb.webui.conf
```

> This is a **one-time manual step**. After this, every share you create or modify through
> the WebUI will be written to `smb.webui.conf` and picked up by Samba automatically on reload.
> You can name the file anything (e.g., `smb.casaos.conf`) — just keep it consistent between
> your `smb.conf` include directive and the `SAMBA_INCLUDE_CONF_PATH` environment variable.

---

## 🚀 Quick Start

### Option A — Local Development (Windows / macOS / Linux, no Docker needed)

Runs in **Mock mode**: the full UI is functional with an in-memory Samba simulation.

**Prerequisites:** [uv](https://docs.astral.sh/uv/) · Python 3.11+

```bash
# 1. Clone and enter the repository
git clone https://github.com/yourname/samba-nice-webui
cd samba-nice-webui

# 2. Copy the environment template
cp .env.example .env          # Windows: copy .env.example .env

# 3. Install dependencies
uv sync --extra dev

# 4. Start the development server
uv run python -m src.main
```

Open **http://localhost:8080** — default credentials: `admin` / `adminpassword`

---

### Option B — Docker Test Environment (isolated Samba in containers)

Spins up a real Samba daemon + WebUI container pair, fully isolated from your host.
Ideal for end-to-end testing or exploring the Linux backend on Windows with Docker Desktop.

```bash
# Remove old volumes to ensure a clean smb.conf is generated
docker compose -f docker-compose.test.yml down -v

# Build and start both containers
docker compose -f docker-compose.test.yml up --build
```

| Endpoint | URL |
|---|---|
| WebUI | http://localhost:8080 |
| Samba (SMB) | `\\localhost:1445\<share_name>` (Windows Explorer) |

> No manual `smb.conf` editing is required for the test environment — the `docker-compose.test.yml`
> bootstraps a minimal `smb.conf` with the `include` directive already in place.

---

### Option C — Production Deployment (Linux Host)

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set SAMBA_BACKEND=linux, strong WEBUI_SECRET_KEY, real paths

# 2. Perform the one-time smb.conf include setup (see prerequisite section above)

# 3. Start the container
docker compose up -d
```

The container mounts `/etc/samba`, `/var/run/samba`, and your storage roots from the host.
See [`docker-compose.yml`](docker-compose.yml) for volume and environment details.

---

## ⚙️ Configuration Reference

All settings are loaded from environment variables or a `.env` file.
Copy `.env.example` to `.env` to get started.

| Variable | Default | Description |
|---|---|---|
| `WEBUI_HOST` | `0.0.0.0` | Interface the WebUI binds to |
| `WEBUI_PORT` | `8080` | HTTP port |
| `WEBUI_ADMIN_USER` | `admin` | Login username |
| `WEBUI_ADMIN_PASSWORD` | `adminpassword` | Login password — **change in production** |
| `WEBUI_SECRET_KEY` | *(insecure default)* | Session signing key — **must be changed** |
| `SAMBA_INCLUDE_CONF_PATH` | `/etc/samba/smb.webui.conf` | The only file this app reads/writes |
| `SAMBA_BACKUP_DIR` | `/etc/samba/.backups` | Directory for timestamped config snapshots |
| `SAMBA_PID_FILE` | `/var/run/samba/smbd.pid` | `smbd` master PID file for `SIGHUP` reload |
| `ALLOWED_STORAGE_ROOTS` | `/storage` | Comma-separated storage root paths (security boundary) |
| `SAMBA_BACKEND` | `mock` | `linux` for production, `mock` for local dev |

---

## 🛡️ Security Model

- **No Docker socket** — the container cannot control the host Docker daemon.
- **No `privileged` mode** — the container runs with default capabilities.
- **No shell injection** — all subprocess calls use list arguments (`subprocess.run([...])`).
- **Filesystem isolation** — `Path.resolve().is_relative_to()` prevents path traversal out of storage roots.
- **Minimal write scope** — only the dedicated include file and backup directory are ever written to.
- **SIGHUP reload** — uses shared PID namespace (`pid: "service:samba-server"`) instead of `docker exec` or socket access.

---

## 🧪 Running Tests

```bash
uv run pytest tests/ -v
```

Tests use the `MockSambaBackend` and temporary directories — no Samba installation required.

---

## 📂 Project Structure

```
samba-nice-webui/
├── src/
│   ├── main.py              # Application entry point & route wiring
│   ├── config.py            # Pydantic settings (env → typed config)
│   ├── core/
│   │   ├── models.py        # Shared data models (ShareConfig, ServerStatus, …)
│   │   ├── security.py      # Path traversal protection & auth helpers
│   │   └── backup.py        # Timestamped snapshot manager
│   ├── samba/
│   │   ├── backend.py       # Abstract SambaBackend interface
│   │   ├── linux_backend.py # Production Linux host implementation
│   │   ├── mock_backend.py  # In-memory mock for local development
│   │   └── parser.py        # INI conf parser & serializer
│   ├── storage/
│   │   └── dir_manager.py   # Bounded directory manager
│   └── ui/
│       ├── layout.py        # Shared page shell & navigation
│       ├── auth_page.py     # Login page
│       ├── dashboard_page.py
│       ├── shares_page.py
│       ├── storage_page.py
│       └── backup_page.py
├── tests/                   # pytest unit + integration tests
├── Dockerfile
├── docker-compose.yml       # Production deployment
├── docker-compose.test.yml  # Isolated test environment
├── .env.example             # Environment variable template
└── pyproject.toml           # uv / hatchling project definition
```
