import os
import shutil
import tempfile
from pathlib import Path
import pytest

from src.core.backup import BackupManager
from src.core.models import ShareConfig, ValidationResult
from src.samba.linux_backend import LinuxHostSambaBackend
from src.samba.parser import serialize_all_shares
from src.storage.dir_manager import StorageDirectoryManager


@pytest.fixture
def temp_workspace():
    # 1. Allocate temporary directory for isolated test execution
    temp_dir = Path(tempfile.mkdtemp(prefix="samba_test_"))
    conf_dir = temp_dir / "etc_samba"
    include_conf = conf_dir / "smb.webui.conf"
    backups = conf_dir / ".backups"
    storage = temp_dir / "storage"
    pid_file = temp_dir / "smbd.pid"

    conf_dir.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)
    storage.mkdir(parents=True, exist_ok=True)

    # Point the PID file at the test process so status checks see a live daemon
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

    yield {
        "root": temp_dir,
        "include_conf_path": include_conf,
        "backup_dir": backups,
        "storage_root": storage,
        "pid_file": pid_file,
    }

    # 2. Cleanup workspace after test completion
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def backup_mgr(temp_workspace):
    return BackupManager(
        backup_dir=temp_workspace["backup_dir"],
        include_conf_path=temp_workspace["include_conf_path"],
    )


@pytest.fixture
def linux_backend(temp_workspace, backup_mgr, monkeypatch):
    backend = LinuxHostSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["pid_file"],
        backup_manager=backup_mgr,
    )

    # 1. Stub external process boundaries: no SIGHUP, no Samba binary in unit CI
    monkeypatch.setattr("src.samba.linux_backend.os.kill", lambda _pid, _sig: None)
    monkeypatch.setattr(
        backend,
        "validate_config",
        lambda _path: ValidationResult(is_valid=True, message="Validation stubbed."),
    )
    monkeypatch.setattr(backend, "reload_service", lambda: True)

    # 2. Seed the share that the removed mock backend used to create on first run
    public_share = ShareConfig(
        name="public",
        path="/storage/public",
        comment="Public Storage",
        read_only=False,
        browsable=True,
        guest_ok=True,
        conf_file=temp_workspace["include_conf_path"].name,
    )
    temp_workspace["include_conf_path"].write_text(
        serialize_all_shares([public_share]),
        encoding="utf-8",
    )

    return backend


@pytest.fixture
def storage_mgr(temp_workspace):
    return StorageDirectoryManager([str(temp_workspace["storage_root"])])
