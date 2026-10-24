import subprocess

import pytest

from src.core.models import ShareConfig, ValidationResult
from src.samba.linux_backend import LinuxHostSambaBackend


def test_backend_crud_lifecycle(linux_backend):
    # 1. Verify initial status
    status = linux_backend.get_status()
    assert status.is_running is True

    # 2. Add new share
    new_share = ShareConfig(
        name="finance",
        path="/storage/finance",
        comment="Finance records",
        read_only=True,
        browsable=True,
        guest_ok=False
    )
    result = linux_backend.save_share(new_share)
    assert result.is_valid is True

    # 3. Retrieve share
    saved = linux_backend.get_share("finance")
    assert saved is not None
    assert saved.name == "finance"
    assert saved.path == "/storage/finance"
    assert saved.read_only is True

    # 4. List all shares
    shares = linux_backend.list_shares()
    names = [s.name for s in shares]
    assert "finance" in names

    # 5. Delete share
    deleted = linux_backend.delete_share("finance")
    assert deleted is True

    assert linux_backend.get_share("finance") is None


def test_delete_records_history_entry(linux_backend, backup_mgr):
    # 1. Delete the seeded share and verify a new history entry is recorded
    previous_ids = {snapshot.snapshot_id for snapshot in backup_mgr.list_snapshots()}
    assert linux_backend.delete_share("public") is True

    snapshots = backup_mgr.list_snapshots()
    new_snapshots = [s for s in snapshots if s.snapshot_id not in previous_ids]

    assert new_snapshots
    assert snapshots[0].description == "Deleted share 'public'"


def test_undo_deleted_share_restores_it(linux_backend, backup_mgr):
    # 1. Delete the seeded share
    assert linux_backend.delete_share("public") is True
    deletion_entry = backup_mgr.list_snapshots()[0]
    assert deletion_entry.description == "Deleted share 'public'"

    # 2. Undo the deletion: share returns and the deletion entry disappears
    snapshot_count = len(backup_mgr.list_snapshots())
    assert backup_mgr.undo_change(deletion_entry.snapshot_id) is True
    assert linux_backend.get_share("public") is not None
    assert len(backup_mgr.list_snapshots()) == snapshot_count - 1
    assert deletion_entry.snapshot_id not in {
        snapshot.snapshot_id for snapshot in backup_mgr.list_snapshots()
    }


def test_create_rejects_duplicate_name(linux_backend, backup_mgr):
    # 1. The seeded 'public' share must not be overwritten by a new create
    before = {share.name: share for share in linux_backend.list_shares()}
    snapshot_count = len(backup_mgr.list_snapshots())

    result = linux_backend.save_share(
        ShareConfig(name="public", path="/storage/other", comment="Duplicate")
    )

    assert result.is_valid is False
    assert "already exists" in result.message
    after = {share.name: share for share in linux_backend.list_shares()}
    assert after["public"].path == before["public"].path
    assert len(backup_mgr.list_snapshots()) == snapshot_count


def test_create_rejects_duplicate_name_case_insensitive(linux_backend):
    # 1. Samba section names are treated case-insensitively
    result = linux_backend.save_share(
        ShareConfig(name="Public", path="/storage/other")
    )

    assert result.is_valid is False
    assert linux_backend.get_share("public") is not None
    assert [share.name for share in linux_backend.list_shares()].count("Public") == 0


def test_update_with_original_name_keeps_single_entry(linux_backend):
    # 1. Create a share, then update its fields through original_name
    assert linux_backend.save_share(
        ShareConfig(name="finance", path="/storage/finance", comment="Old")
    ).is_valid

    result = linux_backend.save_share(
        ShareConfig(name="finance", path="/storage/finance", comment="Updated"),
        original_name="finance",
    )

    assert result.is_valid is True
    shares = [share for share in linux_backend.list_shares() if share.name == "finance"]
    assert len(shares) == 1
    assert shares[0].comment == "Updated"


def test_rename_share_preserves_configuration(linux_backend):
    # 1. Create a share with non-default fields and custom options
    original = ShareConfig(
        name="finance",
        path="/storage/finance",
        comment="Finance records",
        read_only=True,
        valid_users="alice",
    )
    assert linux_backend.save_share(original).is_valid

    # 2. Rename it while preserving the path and advanced options
    renamed = ShareConfig(
        name="finance_2026",
        path="/storage/finance",
        comment="Finance records 2026",
        read_only=True,
        valid_users="alice",
        extra_options={"veto files": "/tmp/*"},
    )
    result = linux_backend.save_share(renamed, original_name="finance")

    assert result.is_valid is True
    assert linux_backend.get_share("finance") is None
    saved = linux_backend.get_share("finance_2026")
    assert saved is not None
    assert saved.path == "/storage/finance"
    assert saved.comment == "Finance records 2026"
    assert saved.read_only is True
    assert saved.valid_users == "alice"
    assert saved.extra_options == {"veto files": "/tmp/*"}
    assert linux_backend.get_share("public") is not None


def test_rename_records_rename_history_entry(linux_backend, backup_mgr):
    # 1. Create and rename a share, then inspect the newest history entry
    assert linux_backend.save_share(
        ShareConfig(name="finance", path="/storage/finance")
    ).is_valid
    assert linux_backend.save_share(
        ShareConfig(name="finance_2026", path="/storage/finance"),
        original_name="finance",
    ).is_valid

    assert backup_mgr.list_snapshots()[0].description == (
        "Renamed share 'finance' to 'finance_2026'"
    )


def test_rename_rejects_collision_with_another_share(linux_backend):
    # 1. Prepare two shares, then try to rename one onto the other's name
    assert linux_backend.save_share(
        ShareConfig(name="alpha", path="/storage/alpha")
    ).is_valid
    assert linux_backend.save_share(
        ShareConfig(name="beta", path="/storage/beta")
    ).is_valid

    result = linux_backend.save_share(
        ShareConfig(name="beta", path="/storage/alpha"),
        original_name="alpha",
    )

    assert result.is_valid is False
    assert "already exists" in result.message
    assert linux_backend.get_share("alpha") is not None
    assert linux_backend.get_share("beta") is not None


def test_update_unknown_original_name_fails(linux_backend):
    # 1. A stale edit dialog must not silently create a new share
    result = linux_backend.save_share(
        ShareConfig(name="ghost", path="/storage/ghost"),
        original_name="missing",
    )

    assert result.is_valid is False
    assert "no longer exists" in result.message
    assert linux_backend.get_share("ghost") is None


@pytest.mark.parametrize("invalid_name", ["global", "homes", "printers", "   "])
def test_rejects_invalid_or_reserved_share_names(linux_backend, backup_mgr, invalid_name):
    # 1. Invalid names return a validation result instead of raising
    snapshot_count = len(backup_mgr.list_snapshots())
    result = linux_backend.save_share(
        ShareConfig(name=invalid_name, path="/storage/invalid")
    )

    assert result.is_valid is False
    assert len(backup_mgr.list_snapshots()) == snapshot_count


def test_validate_config_accepts_testparm_success(monkeypatch, temp_workspace, backup_mgr):
    # 1. A zero exit code from testparm marks the configuration as valid
    def fake_run(args, **kwargs):
        assert args[0] == "testparm"
        return subprocess.CompletedProcess(args, 0, "Loaded services file OK.", "")

    monkeypatch.setattr("src.samba.linux_backend.subprocess.run", fake_run)
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["pid_file"],
        backup_manager=backup_mgr,
    )

    result = backend.validate_config(temp_workspace["include_conf_path"])

    assert result.is_valid is True
    assert "Loaded services file OK" in result.message


def test_validate_config_reports_testparm_failure(monkeypatch, temp_workspace, backup_mgr):
    # 1. A non-zero exit code surfaces testparm's error output
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Error parsing parameter")

    monkeypatch.setattr("src.samba.linux_backend.subprocess.run", fake_run)
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["pid_file"],
        backup_manager=backup_mgr,
    )

    result = backend.validate_config(temp_workspace["include_conf_path"])

    assert result.is_valid is False
    assert result.message == "Error parsing parameter"


def test_validate_config_reports_missing_testparm(monkeypatch, temp_workspace, backup_mgr):
    # 1. A missing binary must fail validation instead of raising
    def fake_run(args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("src.samba.linux_backend.subprocess.run", fake_run)
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["pid_file"],
        backup_manager=backup_mgr,
    )

    result = backend.validate_config(temp_workspace["include_conf_path"])

    assert result.is_valid is False
    assert "not found" in result.message


def test_get_status_reports_stopped_without_pid_file(temp_workspace, backup_mgr):
    # 1. Without a PID file the daemon is reported as stopped
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["root"] / "missing.pid",
        backup_manager=backup_mgr,
    )

    status = backend.get_status()

    assert status.is_running is False
    assert status.pid is None


def test_save_keeps_configuration_when_validation_fails(
    linux_backend,
    backup_mgr,
    temp_workspace,
    monkeypatch,
):
    # 1. Snapshot the configuration and history before the rejected save
    include_conf = temp_workspace["include_conf_path"]
    before_content = include_conf.read_text(encoding="utf-8")
    snapshot_count = len(backup_mgr.list_snapshots())

    # 2. Reject the configuration at the validation boundary
    monkeypatch.setattr(
        linux_backend,
        "validate_config",
        lambda _path: ValidationResult(is_valid=False, message="Error parsing parameter"),
    )

    result = linux_backend.save_share(
        ShareConfig(name="broken", path="/storage/broken")
    )

    # 3. Nothing may be written, snapshotted, or left behind as a temp file
    assert result.is_valid is False
    assert result.message == "Error parsing parameter"
    assert include_conf.read_text(encoding="utf-8") == before_content
    assert linux_backend.get_share("broken") is None
    assert len(backup_mgr.list_snapshots()) == snapshot_count
    assert not include_conf.with_name(f".tmp_{include_conf.name}").exists()


def test_get_share_is_case_insensitive(linux_backend):
    # 1. Samba section names ignore case and surrounding whitespace
    assert linux_backend.get_share("PUBLIC") is not None
    assert linux_backend.get_share("PUBLIC").name == "public"
    assert linux_backend.get_share("  public  ").name == "public"
    assert linux_backend.get_share("unknown") is None


def test_delete_unknown_share_returns_false(linux_backend, backup_mgr):
    # 1. Deleting a missing share must not rewrite the file or record history
    snapshot_count = len(backup_mgr.list_snapshots())

    assert linux_backend.delete_share("missing") is False
    assert len(backup_mgr.list_snapshots()) == snapshot_count


def test_reload_service_without_pid_file_returns_false(temp_workspace, backup_mgr):
    # 1. A missing PID file means there is nothing to signal
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["root"] / "missing.pid",
        backup_manager=backup_mgr,
    )

    assert backend.reload_service() is False
    assert backend.last_reloaded_at is None


def test_reload_service_with_invalid_pid_returns_false(temp_workspace, backup_mgr):
    # 1. A corrupt PID file is a reload failure, not an exception
    pid_file = temp_workspace["root"] / "broken.pid"
    pid_file.write_text("not-a-pid", encoding="utf-8")
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=pid_file,
        backup_manager=backup_mgr,
    )

    assert backend.reload_service() is False
    assert backend.last_reloaded_at is None
