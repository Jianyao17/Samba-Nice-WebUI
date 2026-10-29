import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from src.core.models import SambaGroup, SambaUser, UserOperationResult
from src.samba.backend import SambaBackend
from src.samba.user_backend import SambaUserBackend


_USERNAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_.-]*$")
_NOLOGIN_SHELLS = {"/sbin/nologin", "/usr/sbin/nologin"}
_MAX_NAME_LENGTH = 32
_SYSTEM_GID_MAX = 999


@dataclass
class _PasswdEntry:
    """
    Minimal view of one ``/etc/passwd`` record.
    """

    username: str
    uid: int
    gid: int
    shell: str


@dataclass
class _GroupEntry:
    """
    Minimal view of one ``/etc/group`` record.
    """

    name: str
    gid: int
    members: list[str]


def _decode(value: object) -> str:
    """
    Decode subprocess output that may be bytes or text.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return ""


def normalize_name(name: str) -> str:
    """
    Normalize a username or group name to lowercase.
    """
    return (name or "").strip().lower()


def validate_name(name: str, kind: str = "Name") -> Optional[str]:
    """
    Return a validation error for an invalid user or group name, else ``None``.
    """
    if not name:
        return f"{kind} is required."
    if len(name) > _MAX_NAME_LENGTH:
        return f"{kind} cannot be longer than {_MAX_NAME_LENGTH} characters."
    if not _USERNAME_PATTERN.fullmatch(name):
        return (
            f"{kind} must start with a letter or underscore and may only contain "
            "lowercase letters, numbers, '-', '_' and '.'."
        )
    return None


def split_share_principals(value: str) -> list[str]:
    """
    Split a Samba access list into lowercase principals.
    """
    return [token.lower() for token in re.split(r"[\s,]+", value or "") if token]


def find_share_references(shares: list, principal: str) -> list[str]:
    """
    Return the names of shares that reference a user or ``@group`` principal.
    """
    target = principal.lower()
    conflicts: list[str] = []
    for share in shares:
        tokens = split_share_principals(share.valid_users) + split_share_principals(
            share.write_list
        )
        if target in tokens:
            conflicts.append(share.name)
    return conflicts


class LinuxSambaUserBackend(SambaUserBackend):
    """
    Linux implementation of Samba user and group management.

    All system mutations go through argument-list subprocess calls. Identity
    files are injectable so unit tests never touch the real host database.
    """

    def __init__(
        self,
        samba_backend: SambaBackend,
        reload_callback: Optional[Callable[[], bool]] = None,
        passwd_file: Optional[Path] = None,
        group_file: Optional[Path] = None,
        samba_conf_path: Optional[Path] = None,
        nologin_shell: str = "/sbin/nologin",
    ):
        # 1. Keep share state and reload behaviour pluggable
        self.samba_backend = samba_backend
        self.reload_callback = reload_callback or samba_backend.reload_service

        # 2. Identity files are configurable for tests and containers
        self.passwd_file = Path(passwd_file) if passwd_file else Path("/etc/passwd")
        self.group_file = Path(group_file) if group_file else Path("/etc/group")
        self.samba_conf_path = (
            Path(samba_conf_path) if samba_conf_path else None
        )
        self.nologin_shell = nologin_shell

    # ------------------------------------------------------------------
    # Subprocess and identity file helpers
    # ------------------------------------------------------------------

    def _run(
        self,
        args: list[str],
        password: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """
        Run a system command and return ``(returncode, stdout, stderr)``.
        """
        try:
            result = subprocess.run(
                args,
                input=password.encode("utf-8") if password is not None else None,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return 127, "", f"Required binary '{args[0]}' was not found."

        return (
            result.returncode,
            _decode(result.stdout),
            _decode(result.stderr),
        )

    def _reload_service(self) -> None:
        """
        Signal smbd to reload after a security-relevant change.
        """
        try:
            self.reload_callback()
        except Exception:  # pragma: no cover - defensive process boundary
            pass

    def _pdbedit_args(self, *args: str) -> list[str]:
        """
        Build a pdbedit command targeting the configured Samba config.
        """
        command = ["pdbedit"]
        if self.samba_conf_path is not None:
            command += ["-s", str(self.samba_conf_path)]
        return command + list(args)

    def _smbpasswd_args(self, *args: str) -> list[str]:
        """
        Build a smbpasswd command targeting the configured Samba config.
        """
        command = ["smbpasswd"]
        if self.samba_conf_path is not None:
            command += ["-c", str(self.samba_conf_path)]
        return command + list(args)

    def _read_passwd(self) -> dict[str, _PasswdEntry]:
        """
        Parse the configured passwd file into lowercase-keyed entries.
        """
        entries: dict[str, _PasswdEntry] = {}
        try:
            content = self.passwd_file.read_text(encoding="utf-8")
        except OSError:
            return entries

        for line in content.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) < 7:
                continue
            try:
                uid = int(parts[2])
                gid = int(parts[3])
            except ValueError:
                continue
            username = parts[0].strip().lower()
            if username:
                entries[username] = _PasswdEntry(
                    username=username,
                    uid=uid,
                    gid=gid,
                    shell=parts[6].strip(),
                )
        return entries

    def _read_groups(self) -> dict[str, _GroupEntry]:
        """
        Parse the configured group file into lowercase-keyed entries.
        """
        entries: dict[str, _GroupEntry] = {}
        try:
            content = self.group_file.read_text(encoding="utf-8")
        except OSError:
            return entries

        for line in content.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) < 4:
                continue
            try:
                gid = int(parts[2])
            except ValueError:
                continue
            name = parts[0].strip().lower()
            if not name:
                continue
            members = [
                member.strip().lower()
                for member in parts[3].split(",")
                if member.strip()
            ]
            entries[name] = _GroupEntry(name=name, gid=gid, members=members)
        return entries

    def _samba_accounts(self) -> dict[str, bool]:
        """
        Return Samba accounts mapped to their enabled state.
        """
        # 1. Prefer verbose output so the disabled flag can be read
        returncode, stdout, _ = self._run(self._pdbedit_args("-L", "-v"))
        accounts: dict[str, bool] = {}
        if returncode == 0:
            current: Optional[str] = None
            for line in stdout.splitlines():
                user_match = re.match(r"\s*Unix username:\s*(\S+)", line)
                if user_match:
                    current = user_match.group(1).strip().lower()
                    accounts[current] = True
                    continue

                flag_match = re.match(r"\s*Account Flags:\s*\[([^\]]*)\]", line)
                if flag_match and current and "D" in flag_match.group(1).upper():
                    accounts[current] = False

        if accounts:
            return accounts

        # 2. Fall back to the plain listing when verbose output is unavailable
        returncode, stdout, _ = self._run(self._pdbedit_args("-L"))
        if returncode != 0:
            return accounts

        for line in stdout.splitlines():
            if ":" not in line:
                continue
            username = line.split(":", 1)[0].strip().lower()
            if username:
                accounts[username] = True
        return accounts

    def _reject_referenced(self, principal: str, kind: str, name: str) -> Optional[str]:
        """
        Return an error when active shares still reference a principal.
        """
        conflicts = find_share_references(self.samba_backend.list_shares(), principal)
        if not conflicts:
            return None

        shares = ", ".join(f"'{share}'" for share in conflicts)
        return (
            f"Cannot delete {kind} '{name}' because it is referenced by "
            f"active share(s): {shares}. Remove it from valid users / write list first."
        )

    @staticmethod
    def _failure_detail(returncode: int, stdout: str, stderr: str) -> str:
        """
        Build a compact error detail from a failed system command.
        """
        detail = (stderr or stdout).strip()
        if detail:
            return detail
        return f"command exited with status {returncode}"

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    def list_users(self) -> list[SambaUser]:
        """
        List every Samba account with status and group memberships.
        """
        accounts = self._samba_accounts()
        if not accounts:
            return []

        groups = self._read_groups()
        passwd_entries = self._read_passwd()
        group_by_gid = {group.gid: group.name for group in groups.values()}
        group_memberships: dict[str, set[str]] = {}

        # 1. Explicit group members come from the group database
        for group in groups.values():
            for member in group.members:
                if member in accounts:
                    group_memberships.setdefault(member, set()).add(group.name)

        # 2. A user's primary group is recorded in passwd, not /etc/group
        for username in accounts:
            entry = passwd_entries.get(username)
            if entry is None:
                continue
            primary_group = group_by_gid.get(entry.gid)
            if primary_group:
                group_memberships.setdefault(username, set()).add(primary_group)

        return [
            SambaUser(
                username=username,
                enabled=enabled,
                groups=sorted(group_memberships.get(username, set())),
            )
            for username, enabled in sorted(accounts.items())
        ]

    def create_user(self, username: str, password: str) -> UserOperationResult:
        """
        Create a no-login Unix account and register it with Samba.
        """
        clean_name = normalize_name(username)
        validation_error = validate_name(clean_name, "Username")
        if validation_error:
            return UserOperationResult(success=False, message=validation_error)
        if not password:
            return UserOperationResult(success=False, message="Password is required.")

        # 1. Refuse to collide with any pre-existing identity
        if clean_name in self._read_passwd():
            return UserOperationResult(
                success=False,
                message=f"User '{clean_name}' already exists as a Unix account.",
            )
        if clean_name in self._samba_accounts():
            return UserOperationResult(
                success=False,
                message=f"User '{clean_name}' is already registered with Samba.",
            )

        # 2. Create the Unix account and register the Samba password
        returncode, stdout, stderr = self._run(
            ["useradd", "-M", "-s", self.nologin_shell, clean_name]
        )
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to create Unix account '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        password_input = f"{password}\n{password}\n"
        returncode, stdout, stderr = self._run(
            self._smbpasswd_args("-a", "-s", clean_name),
            password=password_input,
        )
        if returncode != 0:
            # Roll back the Unix account so a failed creation leaves no partial state
            self._run(["userdel", clean_name])
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to register Samba password for '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        return UserOperationResult(
            success=True,
            message=f"User '{clean_name}' created and enabled.",
        )

    def set_password(self, username: str, password: str) -> UserOperationResult:
        """
        Replace the Samba password of an existing user.
        """
        clean_name = normalize_name(username)
        if not password:
            return UserOperationResult(success=False, message="Password is required.")
        if clean_name not in self._samba_accounts():
            return UserOperationResult(
                success=False,
                message=f"Samba user '{clean_name}' no longer exists.",
            )

        returncode, stdout, stderr = self._run(
            self._smbpasswd_args("-s", clean_name),
            password=f"{password}\n{password}\n",
        )
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to change password for '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        self._reload_service()
        return UserOperationResult(
            success=True,
            message=f"Password for '{clean_name}' updated.",
        )

    def enable_user(self, username: str) -> UserOperationResult:
        """
        Allow an existing Samba user to authenticate again.
        """
        return self._set_user_state(username, enabled=True)

    def disable_user(self, username: str) -> UserOperationResult:
        """
        Block an existing Samba user from authenticating.
        """
        return self._set_user_state(username, enabled=False)

    def _set_user_state(self, username: str, *, enabled: bool) -> UserOperationResult:
        """
        Toggle the Samba account flag and reload the daemon.
        """
        clean_name = normalize_name(username)
        if clean_name not in self._samba_accounts():
            return UserOperationResult(
                success=False,
                message=f"Samba user '{clean_name}' no longer exists.",
            )

        flag = "-e" if enabled else "-d"
        returncode, stdout, stderr = self._run(
            self._smbpasswd_args(flag, clean_name)
        )
        if returncode != 0:
            action = "enable" if enabled else "disable"
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to {action} '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        self._reload_service()
        state = "enabled" if enabled else "disabled"
        return UserOperationResult(
            success=True,
            message=f"User '{clean_name}' {state}.",
        )

    def delete_user(self, username: str) -> UserOperationResult:
        """
        Remove a Samba account and its no-login Unix account.
        """
        clean_name = normalize_name(username)

        # 1. Refuse delete when active shares still depend on the user
        reference_error = self._reject_referenced(clean_name, "user", clean_name)
        if reference_error:
            return UserOperationResult(success=False, message=reference_error)

        # 2. Only Samba-managed nologin accounts may be removed
        if clean_name not in self._samba_accounts():
            return UserOperationResult(
                success=False,
                message=f"Samba user '{clean_name}' no longer exists.",
            )
        passwd_entry = self._read_passwd().get(clean_name)
        if passwd_entry is None:
            return UserOperationResult(
                success=False,
                message=f"Unix account '{clean_name}' no longer exists.",
            )
        if passwd_entry.shell not in _NOLOGIN_SHELLS:
            return UserOperationResult(
                success=False,
                message=(
                    f"Refusing to delete '{clean_name}': its Unix shell "
                    f"'{passwd_entry.shell}' is not a nologin shell."
                ),
            )

        # 3. Remove the Samba record first, then the Unix account
        returncode, stdout, stderr = self._run(
            self._smbpasswd_args("-x", clean_name)
        )
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to remove Samba account '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        returncode, stdout, stderr = self._run(["userdel", clean_name])
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Samba account '{clean_name}' was removed, but deleting the "
                    f"Unix account failed: "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        self._reload_service()
        return UserOperationResult(
            success=True,
            message=f"User '{clean_name}' deleted.",
        )

    # ------------------------------------------------------------------
    # Group operations
    # ------------------------------------------------------------------

    def list_groups(self) -> list[SambaGroup]:
        """
        List groups that can be used as Samba principals.

        System groups (GID below 1000) are always hidden so distribution-managed
        groups do not clutter the page. Groups with GID 1000 and above are shown,
        including newly created ones that do not have members yet.
        """
        samba_users = set(self._samba_accounts())
        groups = self._read_groups()
        passwd_entries = self._read_passwd()
        group_by_gid = {group.gid: group.name for group in groups.values()}
        primary_members: dict[str, set[str]] = {}

        # Primary group membership lives in passwd, not in the group member list
        for username in samba_users:
            entry = passwd_entries.get(username)
            if entry is None:
                continue
            primary_group = group_by_gid.get(entry.gid)
            if primary_group:
                primary_members.setdefault(primary_group, set()).add(username)

        listed: list[SambaGroup] = []
        for group in groups.values():
            if group.gid <= _SYSTEM_GID_MAX:
                continue
            members = sorted(set(group.members) | primary_members.get(group.name, set()))
            listed.append(
                SambaGroup(
                    name=group.name,
                    gid=group.gid,
                    members=members,
                )
            )

        return sorted(listed, key=lambda group: group.name)

    def create_group(self, name: str) -> UserOperationResult:
        """
        Create a Unix group for use as a Samba share principal.
        """
        clean_name = normalize_name(name)
        validation_error = validate_name(clean_name, "Group name")
        if validation_error:
            return UserOperationResult(success=False, message=validation_error)
        if clean_name in self._read_groups():
            return UserOperationResult(
                success=False,
                message=f"Group '{clean_name}' already exists.",
            )

        returncode, stdout, stderr = self._run(["groupadd", clean_name])
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to create group '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        return UserOperationResult(
            success=True,
            message=f"Group '{clean_name}' created.",
        )

    def add_user_to_group(self, username: str, group: str) -> UserOperationResult:
        """
        Add a Samba-managed user to a group.
        """
        clean_name = normalize_name(username)
        clean_group = normalize_name(group)

        # 1. Validate both sides and the managed-account rule
        if clean_name not in self._samba_accounts():
            return UserOperationResult(
                success=False,
                message=f"Samba user '{clean_name}' no longer exists.",
            )
        passwd_entry = self._read_passwd().get(clean_name)
        if passwd_entry is None or passwd_entry.shell not in _NOLOGIN_SHELLS:
            return UserOperationResult(
                success=False,
                message=(
                    f"User '{clean_name}' is not a Samba-managed nologin account."
                ),
            )
        if clean_group not in self._read_groups():
            return UserOperationResult(
                success=False,
                message=f"Group '{clean_group}' no longer exists.",
            )

        returncode, stdout, stderr = self._run(
            ["usermod", "-aG", clean_group, clean_name]
        )
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to add '{clean_name}' to '{clean_group}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        return UserOperationResult(
            success=True,
            message=f"User '{clean_name}' added to group '{clean_group}'.",
        )

    def remove_user_from_group(self, username: str, group: str) -> UserOperationResult:
        """
        Remove a user from a group.
        """
        clean_name = normalize_name(username)
        clean_group = normalize_name(group)

        group_entry = self._read_groups().get(clean_group)
        if group_entry is None:
            return UserOperationResult(
                success=False,
                message=f"Group '{clean_group}' no longer exists.",
            )

        passwd_entry = self._read_passwd().get(clean_name)
        if passwd_entry is not None and passwd_entry.gid == group_entry.gid:
            return UserOperationResult(
                success=False,
                message=(
                    f"'{clean_name}' belongs to '{clean_group}' as its primary "
                    "group. Change the user's primary group before removing it."
                ),
            )

        returncode, stdout, stderr = self._run(
            ["gpasswd", "-d", clean_name, clean_group]
        )
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to remove '{clean_name}' from '{clean_group}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        return UserOperationResult(
            success=True,
            message=f"User '{clean_name}' removed from group '{clean_group}'.",
        )

    def delete_group(self, name: str) -> UserOperationResult:
        """
        Delete an unused group that is not referenced by any share.
        """
        clean_name = normalize_name(name)

        # 1. Refuse delete when active shares still grant the group
        reference_error = self._reject_referenced(
            f"@{clean_name}", "group", clean_name
        )
        if reference_error:
            return UserOperationResult(success=False, message=reference_error)

        # 2. Protect system groups and non-empty groups
        group_entry = self._read_groups().get(clean_name)
        if group_entry is None:
            return UserOperationResult(
                success=False,
                message=f"Group '{clean_name}' no longer exists.",
            )
        if group_entry.gid <= _SYSTEM_GID_MAX:
            return UserOperationResult(
                success=False,
                message=(
                    f"Refusing to delete '{clean_name}': system group "
                    f"(GID {group_entry.gid})."
                ),
            )

        # Include users whose primary group is this group, not just explicit members
        effective_members = set(group_entry.members)
        for username in self._samba_accounts():
            entry = self._read_passwd().get(username)
            if entry is not None and entry.gid == group_entry.gid:
                effective_members.add(username)

        if effective_members:
            members = ", ".join(sorted(effective_members))
            return UserOperationResult(
                success=False,
                message=(
                    f"Group '{clean_name}' still has members: {members}. "
                    "Remove them first."
                ),
            )

        returncode, stdout, stderr = self._run(["groupdel", clean_name])
        if returncode != 0:
            return UserOperationResult(
                success=False,
                message=(
                    f"Failed to delete group '{clean_name}': "
                    f"{self._failure_detail(returncode, stdout, stderr)}"
                ),
            )

        return UserOperationResult(
            success=True,
            message=f"Group '{clean_name}' deleted.",
        )
