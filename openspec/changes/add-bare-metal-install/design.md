# Design

## Context

See `proposal.md` for motivation and `specs/` for the behavior contract. The current application already talks to host paths: `LinuxHostSambaBackend` writes the managed include file, validates with `testparm`, and sends `SIGHUP` to `smbd`. The managed include file, backup history, and temporary replacement file all live in `/etc/samba`, so atomic replacement and SELinux labeling already work without code changes.

The missing pieces are distribution and host integration: a release artifact that does not require Python or uv on the target, a systemd unit, environment-file generation, and a one-time safe edit of `smb.conf`. Docker remains the isolated deployment path and is not changed by this design.

## Goals / Non-Goals

**Goals:**

- Ship a reproducible x86_64 Linux bundle containing a portable Python runtime, dependencies, and the application.
- Install, update, and remove the application through one `setup.sh` command with no Python, pip, uv, or compiler on the target.
- Run the application as a hardened root systemd service with a narrow write scope.
- Make the optional `smb.conf` include edit safe, idempotent, and reversible.
- Keep all existing Samba parsing, share, backup, storage, and authentication behavior unchanged.

**Non-Goals:**

- `aarch64`, Fedora/RHEL, Arch, `.deb`/`.rpm`, PyInstaller, Nuitka, or a self-update daemon.
- TLS termination, reverse-proxy configuration, firewall changes, or Samba user management.
- Changing the Docker image, Docker Compose files, or the primary `smb.conf` behavior of the running application.

## Decisions

### D1: Bundle a portable CPython instead of freezing with PyInstaller

The release artifact will contain a `python-build-standalone` CPython 3.12 runtime, a virtual environment with locked dependencies, and the installed application. It will not use PyInstaller or Nuitka.

Rationale:

- NiceGUI serves static assets and relies on imports that PyInstaller must discover through hooks. Bundled Python keeps normal imports and normal tracebacks, which makes support and debugging easier.
- The artifact size is similar to a PyInstaller `--onedir` build.
- No runtime dependency on the host Python, pip, uv, or a compiler.
- The build remains reproducible through `uv sync --locked --no-dev --no-editable`.
- PyInstaller would be the choice only if a single executable were a hard requirement; it is not for a systemd service.

Build details:

- Build inside an `ubuntu:22.04` container so the artifact targets glibc 2.35, the oldest supported target in this change.
- Pin the `python-build-standalone` release and the uv version in the build script.
- Build at the final path `/opt/samba-nice-webui` inside the container so virtualenv shebangs and `pyvenv.cfg` point at the path used on the target.
- Set `UV_COMPILE_BYTECODE=1` during the build and `PYTHONDONTWRITEBYTECODE=1` at runtime so the application directory can be read-only.
- Include `VERSION`, `LICENSE`, the `packaging/samba-nice-webui.service` unit, and the runtime directories in the archive.

### D2: Release layout and integrity

Release assets:

```text
samba-nice-webui-<version>-linux-x86_64.tar.gz
samba-nice-webui-setup.sh
SHA256SUMS
```

Archive layout:

```text
samba-nice-webui/
  VERSION
  LICENSE
  samba-nice-webui.service
  python/
  venv/
```

The installer resolves the requested tag (or the latest release through the GitHub API), downloads the archive and `SHA256SUMS`, verifies the SHA256 before extraction, and aborts without touching the installed version on mismatch.

### D3: Console entrypoint

Add a `main()` function to `src/main.py` and a `[project.scripts]` entry:

```toml
[project.scripts]
samba-nice-webui = "src.main:main"
```

The existing `if __name__ in {"__main__", "__mp_main__"}` guard keeps `python -m src.main` working for development. The installed console script is the only entrypoint systemd uses. The top-level `src` package name is acceptable inside the isolated bundle; renaming the package is out of scope.

### D4: Installer structure

`scripts/setup.sh` is a single self-contained Bash script so `curl ... | sudo bash` works without sibling files. It is also sourceable for tests: it defines functions and only calls `main "$@"` when executed directly.

Structure:

- `set -Eeuo pipefail` and a cleanup trap for temporary downloads and staging directories.
- A `run()` wrapper that prints commands under `--dry-run` instead of executing them.
- Preflight checks before any mutation: root, Linux, x86_64, systemd, apt, supported Debian/Ubuntu version.
- Dependency installation through apt: `samba`, `samba-common-bin`, `curl`, `ca-certificates`, `tar`, `openssl`. No Python, pip, or uv packages.
- Download and verify to a temporary directory before stopping the service.
- Extract into `/opt/.samba-nice-webui.new`, then swap with `/opt/samba-nice-webui`.
- Keep the previous installation as `/opt/.samba-nice-webui.previous` until the new service is healthy.
- If the new service fails to start, restore the previous directory, start it, and exit non-zero.
- Create data and configuration directories only when missing.
- Generate the environment file only on first install.
- Write the storage-roots drop-in after the unit is installed.
- Copy the unit from the bundle to `/etc/systemd/system/`, then `daemon-reload`, `enable`, and `start`.
- Run the optional Samba include bootstrap after the application files are in place.
- Verify `systemctl is-active` and print recent journal entries on failure.

Flags:

- `--version <tag>` pins a release; default resolves the latest GitHub release.
- `--admin-user <name>` sets the first-run admin username and skips that question.
- `--admin-password <value>` sets the first-run admin password and skips that question.
- `--allowed-roots <csv>` sets the allowed storage roots and skips that question.
- `--non-interactive` skips all first-run questions and uses flags and defaults.
- `--no-samba-config` skips the `smb.conf` edit.
- `--uninstall` removes the service and application, preserving configuration and data.
- `--purge` with `--uninstall` removes installer-managed configuration, backups, the managed include file, and the include line.
- `--dry-run` prints planned actions without mutation and without prompting.
- `--help` prints usage.

### D4a: First-run prompts

On first install only, the installer asks three questions, in this order, and nothing else:

1. `Admin username [admin]:`
2. `Admin password [leave blank to generate]:` — read with `read -rs` so it is not echoed.
3. `Allowed storage roots [default: /mnt]:` — comma-separated absolute paths.

Prompts read from `/dev/tty`, not stdin, because `curl ... | sudo bash` consumes stdin as the script body. When `/dev/tty` is unavailable, when `--non-interactive` is set, or when `--dry-run` is active, the installer asks nothing and uses the flags, the defaults, and a generated password. An existing `/etc/samba-nice-webui/webui.env` means "not a first install", so update runs never prompt and never regenerate credentials.

Password handling:

- A blank answer generates a 24-character password with `openssl rand`.
- `--admin-password` is accepted for automation, but it is visible in `ps` and shell history, so the prompt or `SAMBA_NICE_ADMIN_PASSWORD` in the environment is preferred. The flag wins only when the environment variable is unset.
- The chosen or generated password is printed once in the final summary.

Storage-root validation:

- Each value must be an absolute path that resolves inside the target filesystem.
- Any path equal to or below `/etc/samba` is rejected.
- `/` is accepted as a root; it grants the service write access to the whole filesystem through `ReadWritePaths=/`.
- Duplicates are collapsed, order is preserved, and missing directories are created with mode `0755`.
- The drop-in and the environment file receive exactly the validated list.

Editing roots after installation:

- Re-running with `--allowed-roots <csv>` backs up `webui.env`, replaces only the `ALLOWED_STORAGE_ROOTS` line, rewrites the drop-in, runs `daemon-reload`, and restarts the service. Credentials and every other setting stay untouched.
- Without `--allowed-roots`, a re-run keeps the existing roots.
- Changing the password after installation is a manual edit of `/etc/samba-nice-webui/webui.env` followed by `systemctl restart samba-nice-webui`, documented in the README.

### D5: Filesystem layout and configuration

```text
/opt/samba-nice-webui/            read-only at runtime
  VERSION
  python/
  venv/
  samba-nice-webui.service

/etc/samba-nice-webui/webui.env   root:root, 0600, not overwritten on update

/etc/systemd/system/samba-nice-webui.service
/etc/systemd/system/samba-nice-webui.service.d/10-storage-roots.conf
                                  generated from the chosen roots, kept on update

/etc/samba/
  smb.conf                        edited only by the installer
  smb.webui.conf                  managed by the application
  .tmp_smb.webui.conf             transient, managed by the application
  .backups/                       history snapshots

/mnt/                             default storage root, edited per install
```

The environment file contains `WEBUI_HOST=0.0.0.0`, `WEBUI_PORT=8080`, the chosen admin user and password, a generated `WEBUI_SECRET_KEY`, `WEBUI_AUTO_RELOAD=false`, the managed include path, backup directory, PID file `/run/samba/smbd.pid`, and `ALLOWED_STORAGE_ROOTS` from the chosen roots, defaulting to `/mnt`.

`/mnt` is the default because it is the conventional mount point for data disks and already exists on supported hosts. The installer does not create `/mnt` itself; it creates only configured roots that are missing, matching `StorageDirectoryManager`, which calls `mkdir(parents=True, exist_ok=True)` on every configured root at startup.

The application reads these through Pydantic settings from the systemd environment. No `.env` file is installed in the application directory.

### D6: Hardened systemd unit

`packaging/samba-nice-webui.service` is versioned with the bundle:

```ini
[Unit]
Description=Samba Nice WebUI
After=network-online.target smbd.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/samba-nice-webui
EnvironmentFile=/etc/samba-nice-webui/webui.env
Environment=PATH=/opt/samba-nice-webui/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/samba-nice-webui/venv/bin/samba-nice-webui
Restart=on-failure
RestartSec=2
UMask=0022
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
NoNewPrivileges=yes
ReadWritePaths=/etc/samba

[Install]
WantedBy=multi-user.target
```

Storage roots are not hardcoded in the unit. The installer writes `/etc/systemd/system/samba-nice-webui.service.d/10-storage-roots.conf`:

```ini
[Service]
ReadWritePaths=/mnt /mnt/media
```

`ReadWritePaths` is additive across the base unit and drop-ins, so each configured root becomes writable without loosening `ProtectSystem=strict` anywhere else. A drop-in also survives updates, because the bundle only replaces `/opt/samba-nice-webui` and the unit file, never the `*.service.d` directory.

Root is required because the application replaces the managed include file, writes backups in `/etc/samba`, reads the `smbd` PID file, and sends `SIGHUP`. `ProtectSystem=strict` makes the application bundle and the rest of the filesystem read-only. Write scope is the managed Samba directory plus the configured storage roots.

`ProtectHome=yes` is safe because the bundled Python lives under `/opt`, not `/root` or `/home`. `UMask=0022` keeps folders created through the Storage page accessible to Samba clients.

### D7: Samba include bootstrap

The installer is the only actor that edits `/etc/samba/smb.conf`; the application keeps its existing invariant.

Algorithm:

1. Refuse to edit when `smb.conf` or its `[global]` section is missing, and print the manual include line.
2. Back up `smb.conf` to `smb.conf.bak.<UTC timestamp>` using `cp -a`.
3. Skip if the exact managed include line already exists.
4. Use an `awk` pass to insert `   include = /etc/samba/smb.webui.conf` as the last line of the first case-insensitive `[global]` section, immediately before the next section or at end of file.
5. Write the result back in place to preserve ownership, group, and mode.
6. Validate with `testparm -s /etc/samba/smb.conf`.
7. On validation failure, restore the backup, exit non-zero, and do not reload Samba.
8. If `smbd` is active, reload it with `systemctl reload smbd`; a reload failure is reported as a warning because the valid configuration applies on the next Samba restart.

`--purge` uses the reverse operation: back up, remove only the managed include line, validate, restore on failure, and reload when possible.

The insertion and removal helpers are functions inside `scripts/setup.sh` so they can be sourced by shell tests without duplicating logic.

### D8: Update, rollback, and uninstall

- Downloads and checksums are completed before the service is stopped.
- The new bundle is extracted to a staging directory.
- The service is stopped, the old directory is renamed to `.previous`, and the new directory is moved into place.
- The service is started and polled for a short period.
- On success, `.previous` is removed.
- On failure, the new directory is removed, `.previous` is restored, the service is started again, and recent logs are printed.
- `--uninstall` stops and disables the unit, removes the unit file, the storage-roots drop-in, and `/opt/samba-nice-webui`, and leaves `/etc/samba-nice-webui`, `/etc/samba/smb.webui.conf`, `/etc/samba/.backups`, and the configured storage directories intact.
- `--uninstall --purge` also removes the managed env file, backups, include file, and include line after backing up `smb.conf`. It still never deletes a storage directory, because the installer cannot know whether its contents belong to Samba shares.

### D9: Validation and CI

- `shellcheck` and `bash -n` for `scripts/setup.sh`.
- Source-level shell tests for include insertion, idempotency, missing `[global]`, removal, and backup behavior, using fixture `smb.conf` files.
- Source-level shell tests for prompt handling: defaults, custom answers, flag-supplied values, no `/dev/tty`, and invalid storage roots.
- `systemd-analyze verify packaging/samba-nice-webui.service`, plus a check that a generated drop-in with two roots produces both paths in `systemctl show -p ReadWritePaths samba-nice-webui`.
- Bundle smoke test on a clean `ubuntu:22.04` container: extract, run the entrypoint with temporary paths, request `/login`, and confirm a 200 response.
- Release job on `v*` tags: build the bundle, generate `SHA256SUMS`, upload the bundle, installer, and checksums to the GitHub release, and keep the existing Docker publish step.
- Existing unit and real-Samba integration tests continue to run unchanged.

## Risks / Trade-offs

- [Artifact size] A bundled Python runtime is roughly 80-150 MB compressed → Document the size and keep the bundle limited to runtime files, without caches or development dependencies.
- [glibc compatibility] An artifact built on a newer distro may fail on Ubuntu 22.04 → Build in `ubuntu:22.04` and run the bundle smoke test there.
- [Root service] The WebUI can control Samba configuration, which is inherently privileged → Keep the systemd sandbox narrow, document the exposure, and recommend LAN-only access or a reverse proxy.
- [Prompt under `curl | bash`] stdin holds the script, so a naive prompt reads the script body or blocks → Read from `/dev/tty`, detect the missing terminal, and fall back to flags and defaults.
- [Password in argv] `--admin-password` leaks into `ps` and shell history → Prefer the hidden prompt or `SAMBA_NICE_ADMIN_PASSWORD`, and say so in the help text.
- [`/mnt` shared with other data] The default root exposes everything under `/mnt` to the Storage page, including unrelated mounts → Document the exposure and recommend a dedicated subdirectory such as `/mnt/data` when the host keeps other data there.
- [Editing `smb.conf`] A malformed edit can break Samba → Back up, validate with `testparm`, roll back on failure, support `--no-samba-config`, and keep the application itself out of `smb.conf`.
- [GitHub API rate limits] Resolving the latest release can fail → Support `--version`, fail with a clear message, and never fall back to an unverified version.
- [Update interruption] A crash between directory swaps can leave a staging state → Keep the previous directory until the service is healthy and restore it on failure.
- [Top-level `src` package] The console script imports `src.main`, which is a generic name → Acceptable inside the isolated bundle; renaming the package is a separate refactor.
- [HTTP only] Credentials and sessions travel over plain HTTP → Document that the installer does not configure TLS and that the service should not be exposed directly to the internet.

## Migration Plan

- New bare-metal hosts: run the installer, answer the three first-run questions, and optionally let it add the Samba include line.
- Changing data roots later: re-run the installer with `--allowed-roots /mnt/data,/mnt/media`; the environment file is backed up and only that setting changes.
- Docker users moving to bare metal: stop the Compose stack first to avoid port conflicts and concurrent include-file writes, then run the installer. Existing `/etc/samba/smb.webui.conf`, `/etc/samba/.backups`, and include line are detected and reused.
- Rollback: reinstall the previous release with `--version`, or run `--uninstall` to remove the service while preserving configuration and data.
- Verify after deployment: `systemctl status samba-nice-webui`, `journalctl -u samba-nice-webui`, `testparm -s /etc/samba/smb.conf`, and a request to `/login`.
