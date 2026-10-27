# Design

## Context

The current `SambaBackend` / `LinuxHostSambaBackend` pair manages share configuration
(`smb.webui.conf`) via file writes, `testparm` validation, and SIGHUP reload. User and
group management requires a separate set of system commands (`useradd`, `smbpasswd`,
`pdbedit`, `groupadd`, `gpasswd`, `userdel`, `groupdel`) that are more stateful and
require care to avoid touching pre-existing system accounts.

Three deployment modes must be handled uniformly:

| Mode | smbd location | User tools location |
|---|---|---|
| **WebUI-BM** (bare metal) | host | host — direct subprocess |
| **WebUI-Docker** (production container) | host | container (bind-mounted `/etc/passwd`, `/etc/shadow`, `/etc/group`, `/var/lib/samba/private`) |
| **Docker-Test** (dev / Windows) | same container as WebUI | same container as WebUI |

The key architectural insight is that once the bind mounts are in place for WebUI-Docker,
the Python code is **identical** across all three modes — they all call the same
subprocess commands and see the same filesystem layout.

## Goals / Non-Goals

**Goals:**
- Add a `SambaUserBackend` abstract interface mirroring `SambaBackend`
- Implement `LinuxSambaUserBackend` using subprocess calls for all user/group operations
- Protect active shares by refusing to delete users or groups still referenced in `valid users` or `write list`
- Enforce lowercase normalization across UI inputs, backend validations, and system commands
- Add `/users` WebUI page for user and group management
- Modify `setup.sh` and `Dockerfile` to provision required tools
- Collapse `docker-compose.test.yml` to a single all-in-one container using `Dockerfile.test`
- Ship unit tests (stubbed subprocess) and integration tests (real smbd + real useradd)

**Non-Goals:**
- Unix filesystem permissions management (chmod/chown) — Samba handles access control via authentication and share ACLs
- Unix filesystem ACLs (POSIX ACLs via `setfacl`)
- LDAP or Active Directory backends
- SSH or interactive shell access for Samba users
- WebUI-Docker user management via named volumes — bind mounts are the chosen approach

## Decisions

### D1 — Mirror existing backend split: abstract interface + Linux concrete class

**Decision:** Introduce `src/samba/user_backend.py` (abstract `SambaUserBackend`) and
`src/samba/linux_user_backend.py` (concrete `LinuxSambaUserBackend`).

**Rationale:** The project already uses this split for share management. Keeping the
same structure makes the code familiar, keeps the abstract interface testable with stubs,
and leaves room for alternative backends (e.g., a mock backend for tests) without changing
callers.

**Alternative considered:** Extend `SambaBackend` / `LinuxHostSambaBackend` with user
management methods. Rejected because it conflates two orthogonal concerns, making the
abstract interface harder to stub independently and the backend class too large.

### D2 — Subprocess model: argument-list calls, no shell, stdin password pipe

**Decision:** All system commands are called via `subprocess.run([...], ...)` with
argument lists (no `shell=True`), capturing stdout/stderr, checking returncode.

**Rationale:** Matches the pattern already used by `validate_config`. Avoids shell
injection, keeps each call auditable, and produces consistent error messages.

**Password pipe:** `smbpasswd -a` and `smbpasswd` (change password) accept the new
password on stdin when `-s` (silent) flag is used. The implementation pipes the
password string as raw UTF-8 bytes to stdin (`input=f"{password}\n{password}\n".encode("utf-8")`),
never via env var or command-line arguments. This handles special characters (spaces,
quotes, symbols, UTF-8) safely without shell-escaping issues and prevents passwords from
appearing in process lists (`ps`).

### D3 — Protect pre-existing accounts and active share references

**Decision:**
1. **Shell-based check**: The system treats a Unix account as "WebUI-managed" if and only if
   its login shell is `/sbin/nologin` or `/usr/sbin/nologin` AND it was registered in Samba
   (`pdbedit -L` includes it). Delete operations check both conditions before proceeding.
   Create operations check `/etc/passwd` for any pre-existing entry with the same name.
2. **Active share reference check**: Before deleting user `u` or group `g`, the backend
   queries `backend.list_shares()`. It parses `valid_users` and `write_list` by splitting
   on commas and whitespace (`re.split(r'[\s,]+', ...)`), stripping whitespace and leading
   `@`, and comparing case-insensitively. If `u` or `@g` is present in any active share,
   deletion is aborted with a user-facing error listing the conflicting share names. Users
   must remove the principal from the share (or delete the share) before deleting the user/group.

**Rationale:** Prevents accidental deletion of system accounts (`root`, `nobody`) and avoids
leaving orphaned user references in Samba configurations.

### D4 — Lowercase normalization

**Decision:** All usernames and group names are normalized to lowercase (`.strip().lower()`)
at the UI layer and before invoking any backend validation or system command.

**Rationale:** Windows and SMB clients are case-insensitive, while Linux is case-sensitive.
Normalizing to lowercase prevents confusing duplicates (e.g. `Alice` vs `alice`) and
guarantees consistent lookup against `/etc/passwd` and Samba's `passdb.tdb`.

### D5 — Docker-Test: collapse to all-in-one via Dockerfile.test

**Decision:** Update `docker-compose.test.yml` to remove the two-container setup and
use a single service built from `Dockerfile.test`. The `CMD` of `Dockerfile.test` is
managed via an entrypoint script that starts `smbd` in the background, then runs the
WebUI process when not in pure-pytest mode.

**Rationale:** `Dockerfile.test` already contains the full Samba stack (`smbd`,
`smbpasswd`, `pdbedit`, `useradd`). Running both smbd and the WebUI in the same
container eliminates cross-container user database synchronisation issues entirely.

### D6 — WebUI-Docker: bind mount user database files from host

**Decision:** The production Docker image documentation and user compose setup
instruct users to bind mount four host paths when user management is desired:
`/etc/passwd`, `/etc/shadow`, `/etc/group`, and `/var/lib/samba/private`.

**Rationale:** These bind mounts allow the containerized WebUI to execute `useradd` and
`smbpasswd` directly against host identity files, using the exact same code path as
bare-metal installations.

### D7 — Directory access delegation via Samba share configuration

**Decision:** Filesystem-level permissions (`chmod`/`chown`) are not managed directly by
the WebUI. Instead, directory access is delegated to Samba configuration parameters
(`force user = root` or dedicated service user, along with `create mask = 0777` and
`directory mask = 0777` as needed).

**Rationale:** Samba's client authentication and share-level ACLs (`valid users`,
`write list`) already provide granular access control. Forcing user ownership at the Samba
share level avoids complex and fragile multi-user POSIX permission setups on disk while
retaining full security at the network share boundary.

### D8 — Service reload on user status change

**Decision:** Disabling, deleting, or changing passwords for Samba users triggers
`reload_service()` (sending SIGHUP to the `smbd` master daemon).

**Rationale:** Signals `smbd` to reload configuration and re-evaluate active client
permissions for subsequent operations.

## Risks / Trade-offs

- **[Active SMB client sessions]** → Disabling a user in Samba database prevents new
  connections, but existing open TCP sessions may remain alive until disconnected or
  re-authenticated. Mitigation: SIGHUP reload re-evaluates configuration, and documented
  behavior notes that existing connections terminate upon session disconnect.

- **[/etc/shadow bind mount security]** → Giving WebUI-Docker write access to the host
  shadow file is a privilege escalation compared to running only smb.webui.conf edits.
  Mitigation: Document clearly in setup instructions; only required for user management
  feature; not enabled by default in the base compose file.

- **[Dockerfile.test CMD change breaks existing pytest run]** → The integration test
  suite runs `pytest` as CMD. Changing CMD to start smbd + webui would break that.
  Mitigation: Use an entrypoint script with `PYTEST_ONLY=1` environment variable
  handling so `docker run --rm samba-nice-test` still runs pytest seamlessly.

- **[useradd availability in production Dockerfile]** → Production image requires `passwd`
  and `samba-common-bin` packages in the runtime stage.
  Mitigation: Add them to the runtime stage apt install and verify build in CI.

## Migration Plan

1. Bare metal users running `setup.sh` get `smbpasswd` and `pdbedit` on next install
   or update (the script installs them if absent).
2. WebUI-Docker users add four bind mounts to their compose file to enable user
   management; existing setups without bind mounts continue to work for share
   management.
3. Docker-Test users running `docker-compose.test.yml` get the all-in-one container
   automatically on next `docker compose up --build`.
4. No data migration is needed — user management starts from the existing system state.
