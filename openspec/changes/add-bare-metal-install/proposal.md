# Proposal

## Why

The application is currently distributed only as a Docker image and Docker Compose stack. Users who want it on a bare Linux host must clone the repository, install a compatible Python and uv, install dependencies, define a systemd service, and edit `smb.conf` manually. That is error-prone and blocks users who do not have Python tooling on the host. This change adds a first-class bare-metal path that downloads a self-contained release bundle and installs it as a hardened systemd service.

## What Changes

- Add a CI-built, self-contained Linux x86_64 release bundle:
  - portable CPython 3.12, all Python dependencies, and the application in one `.tar.gz`;
  - no Python, pip, uv, or compiler required on the target;
  - fixed runtime layout under `/opt/samba-nice-webui`;
  - published per release with a SHA256 checksum.
- Add `scripts/setup.sh`:
  - supports Debian 12/13 and Ubuntu 22.04/24.04 (apt) and refuses unsupported hosts with a clear message;
  - downloads and verifies the x86_64 release bundle;
  - installs under `/opt/samba-nice-webui`, leaving the application read-only at runtime;
  - asks three first-run questions on a terminal: admin username (default `admin`), admin password (blank generates one), and allowed storage roots (default `/mnt`, comma-separated);
  - creates `/etc/samba-nice-webui/webui.env` with the chosen credentials and a generated session secret, mode `0600`;
  - creates `/etc/samba/.backups` for history and any configured storage root that does not exist yet;
  - writes and enables `samba-nice-webui.service` running as root with systemd hardening, plus a `ReadWritePaths` drop-in for the chosen storage roots;
  - optionally adds `include = /etc/samba/smb.webui.conf` as the last line of `[global]` in `/etc/samba/smb.conf`, after backing up the file, validating with `testparm`, and rolling back on failure;
  - supports `--version`, `--admin-user`, `--admin-password`, `--allowed-roots`, `--non-interactive`, `--no-samba-config`, `--uninstall`, `--dry-run`, and non-interactive operation when no terminal is available;
  - prints the access URL and the effective credentials once at the end.
- Serve `scripts/setup.sh` from GitHub Pages at `https://jianyao17.github.io/Samba-Nice-WebUI/setup.sh` and stop uploading it as a release asset, so the documented install command stays short.
- Add a console entrypoint (`samba-nice-webui = "src.main:main"`) and extract `main()` from the `__main__` guard so systemd starts the app through the package entrypoint.
- Keep the managed include file and backup history in `/etc/samba`. Temporary files remain next to the include file, preserving atomic replacement and SELinux labeling.
- Add release and validation automation: shellcheck, `systemd-analyze verify`, a bundle smoke test, release asset upload, Pages deployment, and checksums.
- Update README, `.env.example`, and AGENTS.md with bare-metal install, update, uninstall, security, and troubleshooting notes.
- Docker remains supported and unchanged as the recommended isolated deployment.

**Scope assumptions:**

- v1 targets `x86_64` only. `aarch64`, Fedora/RHEL, Arch, `.deb`/`.rpm`, PyInstaller, Nuitka, and TLS termination are out of scope.
- The installer may edit `smb.conf` once, with backup and validation. The application itself still never writes `smb.conf`.

## Capabilities

### New Capabilities

- `linux-runtime-bundle`: self-contained Linux x86_64 release artifact that includes the runtime and exposes a stable entrypoint, version, and checksum.
- `linux-installer`: one-command bare-metal installation, systemd service lifecycle, optional Samba include bootstrap, update, and uninstall behavior.

### Modified Capabilities

None.

## Impact

- New: `scripts/setup.sh`, release build workflow or script, installer test fixtures, and possibly a packaging entrypoint.
- Changed: `src/main.py` (extract `main()`), `pyproject.toml` (`[project.scripts]`), `.github/workflows/ci.yml` or a new release workflow, `README.md`, `.env.example`, and `AGENTS.md`.
- No changes to Samba parsing, share planning, backup semantics, storage boundaries, authentication, or the Docker image.
- New runtime contract: `samba-nice-webui.service`, `/opt/samba-nice-webui`, `/etc/samba-nice-webui/webui.env`, `/etc/samba/smb.webui.conf`, `/etc/samba/.backups`, and configurable storage roots with `/mnt` as the default.
- Security: the service runs as root with `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `NoNewPrivileges=yes`, `ReadWritePaths=/etc/samba`, and a generated drop-in that adds the configured storage roots.
