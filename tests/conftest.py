import shutil
import tempfile
from pathlib import Path
import pytest

from src.core.backup import BackupManager
from src.samba.mock_backend import MockSambaBackend
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

    # Write dummy smbd PID
    pid_file.write_text("99999\n", encoding="utf-8")

    yield {
        "root": temp_dir,
        "conf_path": conf_dir / "smb.conf",
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
        main_conf_path=temp_workspace["conf_path"]
    )


@pytest.fixture
def mock_backend(temp_workspace, backup_mgr):
    return MockSambaBackend(
        include_conf_path=temp_workspace["include_conf_path"],
        pid_file=temp_workspace["pid_file"],
        backup_manager=backup_mgr,
        main_conf_path=temp_workspace["conf_path"]
    )


@pytest.fixture
def storage_mgr(temp_workspace):
    return StorageDirectoryManager([str(temp_workspace["storage_root"])])
