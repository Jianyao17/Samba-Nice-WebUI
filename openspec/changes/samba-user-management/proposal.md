# Proposal

## Why

The WebUI currently manages Samba share configuration (`smb.webui.conf`) but has no way
to manage the Samba accounts that those shares reference in `valid users` and `write list`.
Administrators must drop to a shell to run `useradd`, `smbpasswd`, and `groupadd` — defeating
the purpose of a GUI. This gap also breaks Docker-based test parity: the test stack
cannot exercise user-gated shares end-to-end without manual container setup.

Filesystem-level permission modifications (chmod/chown) are deliberately omitted: Samba
already handles access control via authentication and share ACLs (`valid users`, `write list`).
Underlying directory and file access is handled cleanly by configuring Samba share parameters
(e.g., `force user = root` or service account, with `create mask = 0777` and
`directory mask = 0777`), avoiding the complexity and fragility of multi-user POSIX permissions.

## What Changes

- **New**: `SambaUserBackend` — an abstract interface (mirroring `SambaBackend`) for
  listing, adding, updating, and removing Samba users and groups.
- **New**: `LinuxSambaUserBackend` — concrete implementation using `useradd`, `groupadd`,
  `usermod`, `userdel`, `groupdel`, `smbpasswd`, and `pdbedit` via subprocess, matching
  the pattern of `LinuxHostSambaBackend`.
- **New**: Delete protection checks — user and group deletion is blocked if the target
  principal is referenced in any active share's `valid users` or `write list` (matching
  tokens separated by commas or whitespace, case-insensitively).
- **New**: Lowercase username normalization — all usernames and group names are enforced
  and normalized to lowercase across UI inputs, backend validations, and system commands.
- **New**: `/users` WebUI page — manage Samba users (add, change password, enable/disable,
  delete) and groups (add, assign members, delete).
- **Modified**: `setup.sh` — installs `samba-common-bin` (for `smbpasswd` and
  `testparm`) and `samba` (for `pdbedit`) as required host dependencies.
- **Modified**: `Dockerfile` (production WebUI-Docker image) — extracts `testparm`
  and `pdbedit` from a `samba` builder stage, and installs `samba-common-bin` plus
  `passwd` (which provides `useradd`, `groupadd`) inside the runtime image.
- **Modified**: `docker-compose.test.yml` — replaces the separate `samba-server` +
  `webui` containers with a single all-in-one container built from `Dockerfile.test`,
  which already contains the full Samba stack.
- **Modified**: `Dockerfile.test` — adds `samba-common-bin`, `passwd` to ensure user
  management tools are available for integration tests.
- **New**: Unit tests for `SambaUserBackend` operations (stub subprocess, assert no
  collisions with pre-existing users/groups, verify share reference delete protection).
- **New**: Integration tests using the Dockerfile.test all-in-one environment that
  create real system users, add them to Samba, assign groups, connect with `smbclient`,
  and verify share access.

## Capabilities

### New Capabilities

- `samba-user-management`: Create, list, update password, enable/disable, and delete
  Samba users (backed by Linux nologin accounts + `smbpasswd`/`pdbedit`). Includes
  lowercase normalization, stdin password piping, and deletion protection when referenced
  by active shares.
- `samba-group-management`: Create, list, assign members, and delete Unix groups used
  as Samba share principals (`@groupname` in `valid users` / `write list`), with deletion
  protection when referenced by active shares.

### Modified Capabilities

- `linux-installer`: The installer must also provision `samba-common-bin` (for
  `smbpasswd`) and `samba` (for `pdbedit`) as required host dependencies alongside
  `smbd`.

## Impact

- **`src/samba/`**: New `user_backend.py` (abstract) and `linux_user_backend.py`
  (concrete), following the same split as `backend.py` / `linux_backend.py`.
- **`src/core/models.py`**: New `SambaUser` and `SambaGroup` Pydantic models.
- **`src/ui/users/`**: New page module (`users_page.py`, `users_components.py`, `users_dialogs.py`).
- **`src/main.py`**: Register `/users` page route and wire `LinuxSambaUserBackend`.
- **`scripts/setup.sh`**: Add `samba-common-bin` and `samba` to the apt dependency list.
- **`Dockerfile`**: Extract `testparm`/`pdbedit` from a `samba` builder stage and add
  `samba-common-bin` + `passwd` to the runtime image.
- **`Dockerfile.test`**: Ensure `passwd` package is present (may already be; verify).
- **`docker-compose.test.yml`**: Restructure to use the `Dockerfile.test` all-in-one
  image instead of two separate containers.
- **`packaging/samba-nice-webui.service`**: Add `ReadWritePaths` for
  `/var/lib/samba/private` (needed when WebUI-Docker bind-mounts it from the host).
- **`tests/unit/test_user_backend.py`**: Unit tests with stubbed subprocess.
- **`tests/integration/test_user_management.py`**: End-to-end tests in the Dockerfile.test
  environment using real `smbd`, `useradd`, `smbpasswd`, and `smbclient`.
