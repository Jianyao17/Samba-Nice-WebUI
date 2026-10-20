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
| **Share Management** | Full CRUD for share configurations, including rename and duplicate-name protection |
| **Directory Picker** | Lazy, expandable folder tree for selecting a share path inside allowed storage roots |
| **SMB Access Address** | Each share displays a copyable `smb://` address (and Windows UNC path when applicable) |
| **Single Include File** | All managed shares live in one dedicated file — the primary `smb.conf` is never touched |
| **Config Validation** | Every change is validated with `testparm` before being applied |
| **Change History & Undo** | Linear configuration history with field-level diff preview and undo that trims newer entries |
| **Zero-Downtime Reload** | Sends `SIGHUP` to the `smbd` master process via shared PID namespace — no Docker socket, no privileged mode |
| **Storage Safety** | Directory browsing and creation is strictly bounded to configured storage roots — each root gets its own browser panel |
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

Before starting this app in **production**, you must add a single
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

# Build, start, and watch both containers
docker compose -f docker-compose.test.yml up --build --watch
```

| Endpoint | URL |
|---|---|
| WebUI | http://localhost:8080 |
| Samba (SMB) | `smb://localhost:1445/<share_name>` (also shown on each share card) |

> No manual `smb.conf` editing is required for the test environment — the `docker-compose.test.yml`
> bootstraps a minimal `smb.conf` with the `include` directive already in place.

---

### Option C — Production Deployment (Linux Host)

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set a strong WEBUI_SECRET_KEY and real paths

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
| `SAMBA_BACKUP_DIR` | `/etc/samba/.backups` | Directory for configuration history entries |
| `SAMBA_PID_FILE` | `/var/run/samba/smbd.pid` | `smbd` master PID file for `SIGHUP` reload |
| `SAMBA_SMB_HOST` | *(empty)* | Public hostname/IP shown in share SMB addresses; empty uses the WebUI request host |
| `ALLOWED_STORAGE_ROOTS` | `/storage` | Comma-separated storage root paths (security boundary); each root appears as its own browser panel on the Storage page |

---

## 🕘 Configuration History

History entries are written to `SAMBA_BACKUP_DIR` using the server's **local time**:

```text
snapshot_<YYYYMMDD>T<HHMMSS>_<sha256[:8]>
```

Example: `snapshot_20261019T200548_4f9a2c7b`

- The short hash is the first 8 characters of the configuration file's SHA-256.
- Each successful save or delete records a history entry. The oldest entry is the starting point.
- If the current include file is identical to the newest entry, no new entry is created.
- `metadata.json` stays intentionally small: entry ID, local timestamp, description, file list, and full file hash.
- The History page computes diffs on demand — added/removed shares plus field-level changes such as `path`, `read only`, `guest ok`, `valid users`, and `extra_options`.
- **Undo** on an entry restores the configuration from before that change, then removes that entry and every newer entry. Undo does not create a new entry, so the timeline stays linear.
- Undo verifies the stored file hash before writing. The active configuration is never read from history; it remains the source of truth.
- If the active file is edited manually, a drift warning appears and the next save/delete records it as a checkpoint.
- Legacy entries named `snapshot_YYYYMMDD_HHMMSS_ffffff` remain readable.

---

## 🛡️ Security Model

- **No Docker socket** — the container cannot control the host Docker daemon.
- **No `privileged` mode** — the container runs with default capabilities.
- **No shell injection** — all subprocess calls use list arguments (`subprocess.run([...])`).
- **Filesystem isolation** — `Path.resolve().is_relative_to()` prevents path traversal out of storage roots.
- **Minimal write scope** — only the dedicated include file and history directory are ever written to.
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
│   │   ├── smb_address.py   # SMB URI / Windows UNC formatting
│   │   ├── config_diff.py   # Share-level diff used by the History page
│   │   └── backup.py        # Linear configuration history manager
│   ├── samba/
│   │   ├── backend.py       # Abstract SambaBackend interface
│   │   ├── linux_backend.py # Production Linux host implementation
│   │   ├── mock_backend.py  # In-memory mock for local development
│   │   ├── share_ops.py     # Shared create/update/rename validation
│   │   └── parser.py        # INI conf parser & serializer
│   ├── storage/
│   │   └── dir_manager.py   # Bounded directory manager
│   └── ui/
│       ├── layout.py        # Shared page shell & navigation
│       ├── auth_page.py     # Login page
│       ├── dashboard_page.py
│       ├── shares/
│       │   ├── shares_page.py        # Share list & page state
│       │   ├── shares_components.py  # Share cards, badges, SMB address
│       │   ├── shares_dialogs.py     # Editor, delete, directory dialog
│       │   └── directory_tree.py     # Lazy expandable folder tree
│       ├── storage/
│       │   ├── storage_page.py       # Storage explorer page
│       │   ├── storage_components.py # List & icon views
│       │   └── storage_dialogs.py    # Folder dialogs
│       └── backup/
│           ├── backup_page.py        # Configuration history page
│           ├── backup_components.py  # History entries & diffs
│           └── backup_dialogs.py     # Undo dialog
├── tests/                   # pytest unit + integration tests
├── Dockerfile
├── docker-compose.yml       # Production deployment
├── docker-compose.test.yml  # Isolated test environment
├── .env.example             # Environment variable template
└── pyproject.toml           # uv / hatchling project definition
```
