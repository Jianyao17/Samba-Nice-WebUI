# Samba-Nice-WebUI

A modern, secure, and lightweight web management interface for Samba on Linux, built with Python and [NiceGUI](https://nicegui.io/).

---

## Key Features

- **Dashboard**: Real-time overview of active Samba shares and service status.
- **Share CRUD Management**: Easily create, view, edit, and delete Samba share configurations.
- **Dedicated Single Include File Support**: Stores all WebUI-managed shares inside a single dedicated include file (e.g., `/etc/samba/smb.webui.conf` or `smb.casaos.conf`). The primary `smb.conf` is never modified directly, preventing risks to host `[global]` directives.
- **Config Validation & Safe Rollback**: Validates every change using `testparm`, creates timestamped backups, and enables single-click rollback.
- **Controlled Host Reload**: Signals daemon reload via `SIGHUP` without container breakout, Docker socket access, or `privileged` mode.
- **Directory Security**: Restricts storage path browsing and directory creation strictly inside allowed storage root directories (`Path.resolve().is_relative_to(...)`).
- **Zero-Helper Single Container**: Deploys as a single non-privileged Docker container.

---

## Architecture Overview

```text
[ Browser ] <---> [ NiceGUI WebUI (Docker Container, Non-Privileged) ]
                         |
                         |-- Validates syntax via internal 'testparm'
                         |-- Reads/Writes /etc/samba/smb.webui.conf
                         |-- Sends SIGHUP to host smbd via shared PID
                         v
                [ Linux Host Samba ] (primary smb.conf includes smb.webui.conf)
```

---

## Local Development (Windows / macOS / Linux)

### Prerequisites
- [uv](https://docs.astral.sh/uv/) installed.
- Python 3.11+.

### Setup & Run in Mock Mode

On development machines without native Linux Samba, the application operates in `mock` mode:

```bash
# 1. Clone repository and copy environment template
cp .env.example .env

# 2. Install dependencies with uv
uv sync --extra dev

# 3. Start local development server (runs with Mock backend)
uv run python -m src.main
```

Then navigate to: **`http://localhost:8080`**  
Default credentials: `admin` / `adminpassword`

---

## Testing with Isolated Samba Environment (Docker Desktop)

To run end-to-end integration tests or explore the WebUI with real Samba binaries on Windows:

```bash
# Start isolated Samba daemon and WebUI containers
docker compose -f docker-compose.test.yml up --build
```

- Open **`http://localhost:8080`** in your browser.
- Samba share port is mapped to `1445:445` for safe testing from Windows Explorer (`\\localhost:1445\<share_name>`).

---

## Production Deployment (Linux Host)

See `docker-compose.yml` for production deployment on Linux hosts.
Mount `/etc/samba`, `/var/run/samba`, and your storage root directory.

```bash
docker compose up -d
```
