"""End-to-end user and group management against a real smbd."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from src.core.models import ShareConfig
from src.samba.linux_user_backend import LinuxSambaUserBackend


_REQUIRED_BINARIES = ("smbd", "smbclient", "smbpasswd", "pdbedit", "useradd", "groupadd")

pytestmark = pytest.mark.skipif(
    any(shutil.which(binary) is None for binary in _REQUIRED_BINARIES)
    or not hasattr(os, "geteuid")
    or os.geteuid() != 0,
    reason="user management integration tests require root plus the Samba/passwd tools",
)


def _unique(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


@pytest.fixture(autouse=True)
def identity_guard():
    """Snapshot identity files and remove leftovers created by a failed test."""
    passwd = Path("/etc/passwd")
    group = Path("/etc/group")
    passwd_before = _lines(passwd)
    group_before = _lines(group)

    yield

    passwd_after = _lines(passwd)
    group_after = _lines(group)
    for line in passwd_before:
        assert line in passwd_after
    for line in group_before:
        assert line in group_after

    # Remove leftovers by name prefix; test names are unique per run.
    before_users = {line.split(":", 1)[0] for line in passwd_before}
    for line in passwd_after:
        name = line.split(":", 1)[0]
        if name.startswith("webui_") and name not in before_users:
            subprocess.run(["userdel", name], capture_output=True, check=False)

    before_groups = {line.split(":", 1)[0] for line in group_before}
    for line in group_after:
        name = line.split(":", 1)[0]
        if name.startswith("webui_") and name not in before_groups:
            subprocess.run(["groupdel", name], capture_output=True, check=False)


@pytest.fixture
def user_backend(backend, samba_server):
    return LinuxSambaUserBackend(
        samba_backend=backend,
        samba_conf_path=samba_server.smb_conf,
    )


def _auth_command(
    port: int,
    share: str,
    username: str,
    password: str,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "smbclient",
            f"//127.0.0.1/{share}",
            "-p",
            str(port),
            "-U",
            f"{username}%{password}",
            "-c",
            "ls",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _share_for_user(name: str, path: str, principal: str) -> ShareConfig:
    return ShareConfig(
        name=name,
        path=path,
        comment="User management integration test",
        read_only=False,
        browsable=True,
        guest_ok=False,
        valid_users=principal,
    )


def test_created_user_can_authenticate_to_a_gated_share(
    backend,
    user_backend,
    samba_server,
):
    username = _unique("webui_")
    share_name = _unique("usershare_")

    assert user_backend.create_user(username, "Passw0rd!x").success
    try:
        assert backend.save_share(
            _share_for_user(share_name, str(samba_server.storage), username)
        ).is_valid
        assert username in {
            user.username for user in user_backend.list_users()
        }

        deadline_ok = False
        for _ in range(50):
            result = _auth_command(
                samba_server.port, share_name, username, "Passw0rd!x"
            )
            if result.returncode == 0:
                deadline_ok = True
                break
        assert deadline_ok, "new Samba user could not authenticate"
    finally:
        backend.delete_share(share_name)
        assert user_backend.delete_user(username).success

    assert username not in Path("/etc/passwd").read_text(encoding="utf-8")


def test_delete_user_is_blocked_while_referenced_by_a_share(
    backend,
    user_backend,
    samba_server,
):
    username = _unique("webui_")
    share_name = _unique("usershare_")

    assert user_backend.create_user(username, "Passw0rd!x").success
    try:
        assert backend.save_share(
            _share_for_user(share_name, str(samba_server.storage), username)
        ).is_valid

        result = user_backend.delete_user(username)

        assert result.success is False
        assert share_name in result.message
        assert username in Path("/etc/passwd").read_text(encoding="utf-8")
    finally:
        backend.delete_share(share_name)
        user_backend.delete_user(username)


def test_password_change_invalidates_the_old_password(
    backend,
    user_backend,
    samba_server,
):
    username = _unique("webui_")
    share_name = _unique("usershare_")

    assert user_backend.create_user(username, "OldPassw0rd!").success
    try:
        assert backend.save_share(
            _share_for_user(share_name, str(samba_server.storage), username)
        ).is_valid
        assert user_backend.set_password(username, "NewPassw0rd!").success

        old_ok = False
        new_ok = False
        for _ in range(50):
            old_result = _auth_command(
                samba_server.port, share_name, username, "OldPassw0rd!"
            )
            new_result = _auth_command(
                samba_server.port, share_name, username, "NewPassw0rd!"
            )
            if new_result.returncode == 0:
                new_ok = True
                old_ok = old_result.returncode == 0
                break
        assert new_ok, "new password was not accepted"
        assert old_ok is False, "old password was still accepted"
    finally:
        backend.delete_share(share_name)
        user_backend.delete_user(username)


def test_disabled_user_cannot_authenticate(
    backend,
    user_backend,
    samba_server,
):
    username = _unique("webui_")
    share_name = _unique("usershare_")

    assert user_backend.create_user(username, "Passw0rd!x").success
    try:
        assert backend.save_share(
            _share_for_user(share_name, str(samba_server.storage), username)
        ).is_valid
        assert user_backend.disable_user(username).success

        authenticated = False
        for _ in range(50):
            result = _auth_command(
                samba_server.port, share_name, username, "Passw0rd!x"
            )
            if result.returncode == 0:
                authenticated = True
                break
            if "NT_STATUS_LOGON_FAILURE" in result.stderr:
                break
        assert authenticated is False
    finally:
        backend.delete_share(share_name)
        user_backend.delete_user(username)


def test_group_principal_grants_access(
    backend,
    user_backend,
    samba_server,
):
    username = _unique("webui_")
    group_name = _unique("webuig_")
    share_name = _unique("groupshare_")

    assert user_backend.create_user(username, "Passw0rd!x").success
    try:
        assert user_backend.create_group(group_name).success
        assert user_backend.add_user_to_group(username, group_name).success
        assert backend.save_share(
            _share_for_user(share_name, str(samba_server.storage), f"@{group_name}")
        ).is_valid

        accessible = False
        for _ in range(50):
            result = _auth_command(
                samba_server.port, share_name, username, "Passw0rd!x"
            )
            if result.returncode == 0:
                accessible = True
                break
        assert accessible, "group member could not authenticate"
    finally:
        backend.delete_share(share_name)
        user_backend.remove_user_from_group(username, group_name)
        user_backend.delete_user(username)
        user_backend.delete_group(group_name)
