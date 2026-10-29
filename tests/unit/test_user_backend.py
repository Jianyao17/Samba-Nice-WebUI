import subprocess
from pathlib import Path

import pytest

from src.core.models import ShareConfig
from src.samba.linux_user_backend import (
    LinuxSambaUserBackend,
    find_share_references,
)


class _FakeSambaBackend:
    def __init__(self, shares=None):
        self.shares = shares or []
        self.reloads = 0

    def list_shares(self):
        return self.shares

    def reload_service(self):
        self.reloads += 1
        return True


class _Runner:
    def __init__(self, samba_users=None):
        self.calls = []
        self.samba_users = samba_users or []

    def _pdbedit_output(self, verbose):
        if not verbose:
            return "".join(f"{user}:1000:{user}\n" for user in self.samba_users)

        blocks = []
        for user in self.samba_users:
            flags = "[U          ]" if user != "disabled" else "[DU         ]"
            blocks.append(
                "---------------\n"
                f"Unix username:        {user}\n"
                f"Account Flags:        {flags}\n"
            )
        return "".join(blocks)

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))

        if args[0] == "pdbedit":
            verbose = "-v" in args
            return subprocess.CompletedProcess(
                args, 0, self._pdbedit_output(verbose), ""
            )

        return subprocess.CompletedProcess(args, 0, "", "")

    def names(self):
        return [call[0][0] for call in self.calls]


def _write_identity(passwd_file: Path, group_file: Path, passwd="", group=""):
    passwd_file.write_text(passwd, encoding="utf-8")
    group_file.write_text(group, encoding="utf-8")


@pytest.fixture
def backend(tmp_path):
    fake = _FakeSambaBackend()
    instance = LinuxSambaUserBackend(
        samba_backend=fake,
        reload_callback=fake.reload_service,
        passwd_file=tmp_path / "passwd",
        group_file=tmp_path / "group",
    )
    _write_identity(instance.passwd_file, instance.group_file)
    return instance


@pytest.fixture
def runner(monkeypatch):
    stub = _Runner()
    monkeypatch.setattr("src.samba.linux_user_backend.subprocess.run", stub)
    return stub


def test_create_user_normalizes_and_pipes_password(backend, runner):
    backend.passwd_file.write_text(
        "root:x:0:0:root:/root:/bin/bash\n", encoding="utf-8"
    )

    result = backend.create_user("Alice", "sëcret pass")

    assert result.success is True
    assert "alice" in result.message

    useradd = next(call for call in runner.calls if call[0][0] == "useradd")
    assert useradd[0] == ["useradd", "-M", "-s", "/sbin/nologin", "alice"]

    smbpasswd = next(call for call in runner.calls if call[0][0] == "smbpasswd")
    assert smbpasswd[0] == ["smbpasswd", "-a", "-s", "alice"]
    assert smbpasswd[1]["input"] == "sëcret pass\nsëcret pass\n".encode("utf-8")


def test_create_user_rejects_duplicate_without_invoking_useradd(backend, runner):
    backend.passwd_file.write_text(
        "alice:x:1000:1000::/home/alice:/sbin/nologin\n", encoding="utf-8"
    )

    result = backend.create_user("alice", "secret")

    assert result.success is False
    assert "already exists" in result.message
    assert "useradd" not in runner.names()


def test_create_user_rejects_invalid_characters(backend, runner):
    result = backend.create_user("bad user!", "secret")

    assert result.success is False
    assert "must start" in result.message
    assert runner.calls == []


def test_delete_user_rejects_share_references_with_mixed_delimiters(backend, runner):
    backend.samba_backend.shares = [
        ShareConfig(
            name="finance",
            path="/storage/finance",
            valid_users="alice, bob",
            write_list="carol alice",
        )
    ]
    runner.samba_users = ["alice"]

    result = backend.delete_user("alice")

    assert result.success is False
    assert "finance" in result.message
    assert runner.calls == []


def test_delete_user_rejects_unmanaged_accounts(backend, runner):
    backend.passwd_file.write_text(
        "root:x:0:0:root:/root:/bin/bash\n", encoding="utf-8"
    )
    runner.samba_users = ["root"]

    result = backend.delete_user("root")

    assert result.success is False
    assert "nologin" in result.message


def test_delete_user_removes_samba_then_unix_account(backend, runner):
    backend.passwd_file.write_text(
        "alice:x:1000:1000::/home/alice:/sbin/nologin\n", encoding="utf-8"
    )
    runner.samba_users = ["alice"]

    result = backend.delete_user("Alice")

    assert result.success is True
    commands = [call[0] for call in runner.calls]
    assert ["smbpasswd", "-x", "alice"] in commands
    assert ["userdel", "alice"] in commands
    assert commands.index(["smbpasswd", "-x", "alice"]) < commands.index(
        ["userdel", "alice"]
    )
    assert backend.samba_backend.reloads == 1


def test_set_password_pipes_utf8_and_reloads(backend, runner):
    runner.samba_users = ["alice"]

    result = backend.set_password("alice", "pässçörd")

    assert result.success is True
    smbpasswd = next(call for call in runner.calls if call[0][0] == "smbpasswd")
    assert smbpasswd[0] == ["smbpasswd", "-s", "alice"]
    assert smbpasswd[1]["input"] == "pässçörd\npässçörd\n".encode("utf-8")
    assert backend.samba_backend.reloads == 1


def test_disable_and_enable_user_reload(backend, runner):
    runner.samba_users = ["alice"]

    disable = backend.disable_user("alice")
    enable = backend.enable_user("alice")

    assert disable.success is True
    assert enable.success is True
    commands = [call[0] for call in runner.calls]
    assert ["smbpasswd", "-d", "alice"] in commands
    assert ["smbpasswd", "-e", "alice"] in commands
    assert backend.samba_backend.reloads == 2


def test_list_users_reads_status_and_groups(backend, runner):
    runner.samba_users = ["alice", "disabled"]
    backend.group_file.write_text(
        "developers:x:1500:alice\n"
        "admins:x:1501:disabled\n",
        encoding="utf-8",
    )

    users = backend.list_users()

    assert [user.username for user in users] == ["alice", "disabled"]
    assert users[0].enabled is True
    assert users[1].enabled is False
    assert users[0].groups == ["developers"]


def test_create_group_normalizes_and_rejects_duplicates(backend, runner):
    backend.group_file.write_text("developers:x:1500:\n", encoding="utf-8")

    duplicate = backend.create_group("Developers")
    created = backend.create_group("Ops")

    assert duplicate.success is False
    assert "already exists" in duplicate.message
    assert created.success is True
    assert ["groupadd", "ops"] in [call[0] for call in runner.calls]


def test_delete_group_rejects_share_reference(backend, runner):
    backend.group_file.write_text("developers:x:1500:\n", encoding="utf-8")
    backend.samba_backend.shares = [
        ShareConfig(
            name="projects",
            path="/storage/projects",
            valid_users="@developers",
        )
    ]

    result = backend.delete_group("developers")

    assert result.success is False
    assert "projects" in result.message


def test_delete_group_rejects_non_empty_group(backend, runner):
    backend.group_file.write_text("developers:x:1500:alice\n", encoding="utf-8")

    result = backend.delete_group("developers")

    assert result.success is False
    assert "still has members" in result.message
    assert "groupdel" not in runner.names()


def test_delete_group_rejects_system_group(backend, runner):
    backend.group_file.write_text("sudo:x:27:\n", encoding="utf-8")

    result = backend.delete_group("sudo")

    assert result.success is False
    assert "system group" in result.message


def test_list_users_and_groups_include_primary_group(backend, runner):
    runner.samba_users = ["alice"]
    backend.passwd_file.write_text(
        "alice:x:1000:1000::/home/alice:/sbin/nologin\n", encoding="utf-8"
    )
    backend.group_file.write_text("alice:x:1000:\n", encoding="utf-8")

    users = backend.list_users()
    groups = backend.list_groups()

    assert users[0].groups == ["alice"]
    assert [(group.name, group.members) for group in groups] == [
        ("alice", ["alice"])
    ]


def test_list_groups_hides_system_groups_with_members(backend, runner):
    runner.samba_users = ["alice"]
    backend.passwd_file.write_text(
        "alice:x:1000:1000::/home/alice:/sbin/nologin\n", encoding="utf-8"
    )
    backend.group_file.write_text(
        "sudo:x:27:alice\nusers:x:100:\ndevelopers:x:1500:\n",
        encoding="utf-8",
    )

    groups = backend.list_groups()

    assert [(group.name, group.gid) for group in groups] == [
        ("developers", 1500)
    ]


def test_delete_group_rejects_primary_group(backend, runner):
    runner.samba_users = ["alice"]
    backend.passwd_file.write_text(
        "alice:x:1000:1000::/home/alice:/sbin/nologin\n", encoding="utf-8"
    )
    backend.group_file.write_text("alice:x:1000:\n", encoding="utf-8")

    result = backend.delete_group("alice")

    assert result.success is False
    assert "still has members" in result.message
    assert "groupdel" not in runner.names()


def test_remove_user_from_primary_group_is_rejected(backend, runner):
    backend.passwd_file.write_text(
        "alice:x:1000:1000::/home/alice:/sbin/nologin\n", encoding="utf-8"
    )
    backend.group_file.write_text("alice:x:1000:\n", encoding="utf-8")

    result = backend.remove_user_from_group("alice", "alice")

    assert result.success is False
    assert "primary group" in result.message
    assert "gpasswd" not in runner.names()


def test_find_share_references_is_case_insensitive():
    shares = [
        ShareConfig(
            name="one",
            path="/one",
            valid_users="ALICE, @Developers",
            write_list="bo b",
        ),
        ShareConfig(name="two", path="/two", valid_users="bob"),
    ]

    assert find_share_references(shares, "alice") == ["one"]
    assert find_share_references(shares, "@developers") == ["one"]
    assert find_share_references(shares, "@missing") == []
