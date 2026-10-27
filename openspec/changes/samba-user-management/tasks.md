# Tasks

## 1. Models and core data structures

- [ ] 1.1 Add `SambaUser` Pydantic model to `src/core/models.py` (fields: `username`,
  `enabled: bool`, `groups: list[str]`) and `SambaGroup` model (fields: `name`,
  `gid: int`, `members: list[str]`); verify `uv run pytest tests/unit/test_parser.py`
  still passes (no regressions from model additions).
- [ ] 1.2 Add `UserOperationResult` Pydantic model (fields: `success: bool`,
  `message: str`) to `src/core/models.py`; used as the uniform return type for all
  user/group mutation operations.

## 2. Abstract user backend interface

- [ ] 2.1 Create `src/samba/user_backend.py` with abstract class `SambaUserBackend`
  declaring methods: `list_users()`, `create_user()`, `set_password()`,
  `enable_user()`, `disable_user()`, `delete_user()`, `list_groups()`,
  `create_group()`, `add_user_to_group()`, `remove_user_from_group()`,
  `delete_group()`; verify the file imports cleanly with
  `uv run python -c "from src.samba.user_backend import SambaUserBackend"`.

## 3. Linux user backend (subprocess implementation)

- [ ] 3.1 Create `src/samba/linux_user_backend.py` with `LinuxSambaUserBackend`
  implementing `SambaUserBackend`. Constructor accepts `SambaBackend` instance (to
  query shares for deletion protection) and reload callback. Implement `list_users()`
  via `pdbedit -L` (returning lowercase usernames) and `list_groups()` via `getent group`,
  filtering to groups with at least one Samba-managed member.
- [ ] 3.2 Implement `create_user()`: normalize username to lowercase (`.strip().lower()`),
  validate regex `[a-z_][a-z0-9_.-]*` and max 32 chars, check `/etc/passwd` for
  pre-existing entry, run `useradd -M -s /sbin/nologin <username>`, pipe password via
  stdin as UTF-8 bytes to `smbpasswd -a -s <username>`; return `UserOperationResult`.
  Verify via unit test (Task 4.1) that duplicate name returns `success=False` without
  invoking `useradd`.
- [ ] 3.3 Implement `set_password()`: verify user in `pdbedit -L`, pipe new password via
  stdin as UTF-8 bytes to `smbpasswd -s <username>`, trigger service reload; return
  `UserOperationResult`. Implement `enable_user()` via `smbpasswd -e` and `disable_user()`
  via `smbpasswd -d` with service reload.
- [ ] 3.4 Implement active share reference validator: helper function that splits
  `valid_users` and `write_list` tokens on commas and whitespace (`re.split(r'[\s,]+', ...)`),
  normalizes to lowercase, and returns the list of share names referencing the given
  username or `@groupname`.
- [ ] 3.5 Implement `delete_user()`: check active share references via Task 3.4 helper and
  return error with share names if referenced; verify shell is `/sbin/nologin` or
  `/usr/sbin/nologin` AND user is in `pdbedit -L`; run `smbpasswd -x <username>`, then
  `userdel <username>`, trigger service reload; return `UserOperationResult`.
- [ ] 3.6 Implement `create_group()`: normalize group name to lowercase, validate regex,
  check `/etc/group` for pre-existing entry, run `groupadd <name>`; return
  `UserOperationResult`.
- [ ] 3.7 Implement `add_user_to_group()` via `usermod -aG <group> <user>`, with
  pre-flight checks that both exist and user is Samba-managed. Implement
  `remove_user_from_group()` via `gpasswd -d <user> <group>`. Implement `delete_group()`:
  check active share references via Task 3.4 helper and reject if referenced; verify
  group is empty and not a pre-existing system group (GID < 1000), then run `groupdel`;
  return `UserOperationResult`.

## 4. Unit tests for user backend

- [ ] 4.1 Create `tests/unit/test_user_backend.py`. Use `monkeypatch` to stub
  `subprocess.run` (return controlled `CompletedProcess` objects) and mock `SambaBackend`.
  Cover:
  - Create user happy path with lowercase normalization.
  - Reject duplicate username and invalid characters.
  - Reject deleting user referenced in active shares (testing comma and space delimiters).
  - Reject deleting root and accounts with non-nologin shells.
  - Set password passing UTF-8 input via stdin.
  - Enable/disable user triggering service reload.
  - Group create with lowercase normalization and duplicate check.
  - Reject deleting group referenced in active shares or non-empty group.
  Verify with `uv run pytest tests/unit/test_user_backend.py -v`.

## 5. Wiring in main and navigation

- [ ] 5.1 Instantiate `LinuxSambaUserBackend` in `src/main.py` alongside the existing
  `LinuxHostSambaBackend`. Add `ensure_supported_runtime()` check for `smbpasswd`
  and `pdbedit` binaries (via `shutil.which`), logging a warning (not a fatal error)
  if absent, so existing deployments without user management continue to start.
  Verify `uv run pytest -v` still passes (no regressions).
- [ ] 5.2 Register `/users` page route in `src/main.py`, passing the user backend.
  Add "Users" link to the navigation in `src/ui/layout.py`. Verify the route exists
  by inspecting the NiceGUI route table in a test or by running the app and checking
  the nav renders.

## 6. Users page UI

- [ ] 6.1 Create `src/ui/users/users_page.py` with `create_users_page(user_backend)`
  factory. Implement a two-tab layout: "Users" tab and "Groups" tab, following the
  pattern of `src/ui/shares/shares_page.py`. Verify the page renders without error
  in the Docker-Test environment.
- [ ] 6.2 Create `src/ui/users/users_components.py`. Implement `render_users_table`
  showing username, status (enabled/disabled badge), group memberships, and action
  buttons (Change Password, Enable/Disable, Delete). Implement `render_groups_table`
  showing group name, member count, and action buttons (Manage Members, Delete).
- [ ] 6.3 Create `src/ui/users/users_dialogs.py`. Implement dialogs for:
  - Add User: username (enforcing lowercase input) and password fields.
  - Change Password: new password field with confirmation.
  - Confirm Delete: displays explicit warning and error if deletion fails due to active
    share references.
  - Manage Group Members: add/remove Samba-managed users to group.
  Verify each dialog can be opened and submitted without error in the Docker-Test environment.

## 7. Integration tests

- [ ] 7.1 Update `Dockerfile.test` to include the `passwd` package (provides `useradd`,
  `groupadd`, `userdel`, `groupdel`) if not already present. Update the CMD to an
  entrypoint script: if `PYTEST_ONLY=1` is set (default for `docker build -f
  Dockerfile.test ... && docker run`), run `pytest -v`; otherwise start `smbd -D`
  then exec the WebUI process. Verify
  `docker build -f Dockerfile.test -t samba-nice-test . && docker run --rm
  samba-nice-test` still exits 0.
- [ ] 7.2 Update `docker-compose.test.yml` to replace the two-container setup with a
  single service using `Dockerfile.test` as the build context, with appropriate
  volumes and environment variables. Verify
  `docker compose -f docker-compose.test.yml up --build` starts correctly and the
  WebUI is reachable on port 8080.
- [ ] 7.3 Create `tests/integration/test_user_management.py`. Tests run only when
  `smbd`, `smbpasswd`, `pdbedit`, and `useradd` are all present (skip otherwise).
  Cover:
  - Create user → `smbclient` can authenticate → share with `valid users` is accessible.
  - Reject deleting user when referenced in active share `valid users = user1`.
  - Delete user after removing from share → user no longer in `pdbedit` or `/etc/passwd`.
  - Change password → old password rejected, new password accepted.
  - Disable user → authentication fails.
  - Group creation and share access via `@groupname`.
  Verify tests pass inside Dockerfile.test:
  `docker build -f Dockerfile.test -t samba-nice-test . &&
  docker run --rm -e PYTEST_ONLY=1 samba-nice-test pytest
  tests/integration/test_user_management.py -v`.
- [ ] 7.4 Verify no pre-existing system users or groups are damaged after the integration
  test run. Add a test fixture that snapshots `/etc/passwd` and `/etc/group` before
  each test and asserts that only the expected new entries were added and all
  pre-existing entries are intact after cleanup. Verify this fixture is invoked in
  every test in `test_user_management.py`.

## 8. Installer and Docker image updates

- [ ] 8.1 Update `scripts/setup.sh`: add `smbpasswd` and `pdbedit` to the binary
  checks after Samba installation; add `samba-common-bin` to the apt install list if
  it is not already pulled in by `samba`. Verify
  `uv run pytest tests/shell/test_installer.py -v` still passes.
- [ ] 8.2 Update `Dockerfile` (production WebUI image): add `samba-common-bin` and
  `passwd` to the runtime-stage apt install block. Verify the production image builds
  successfully and `docker run --rm <image> testparm --version` exits 0 (existing
  smoke check). Verify additionally that `docker run --rm <image> which smbpasswd`
  exits 0.
- [ ] 8.3 Update `packaging/samba-nice-webui.service`: add
  `/var/lib/samba/private` to `ReadWritePaths` so that WebUI-Docker bind-mounted
  `passdb.tdb` writes are allowed under `ProtectSystem=strict`. Verify the service
  unit passes systemd-analyze as documented in AGENTS.md.
- [ ] 8.4 Add documentation (in `README.md` or a `docs/user-management.md`) describing
  the four bind mounts needed for WebUI-Docker user management (`/etc/passwd`,
  `/etc/shadow`, `/etc/group`, `/var/lib/samba/private`) with an annotated compose
  snippet, and a note that the feature degrades gracefully when bind mounts are absent.
  Verify the documented compose snippet is syntactically valid YAML.

## 9. Final integration check

- [ ] 9.1 Run the full test suite `uv run pytest -v` on the host and verify it passes
  with no regressions.
- [ ] 9.2 Run the Dockerfile.test integration suite
  (`docker build -f Dockerfile.test -t samba-nice-test . &&
  docker run --rm -e PYTEST_ONLY=1 samba-nice-test`) and verify all tests pass,
  including the new `test_user_management.py` tests.

## Workflow follow-up

- Archive the change after review and verification are complete.
