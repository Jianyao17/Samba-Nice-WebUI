import os
import shutil

from nicegui import app, ui

from src.config import settings
from src.core.backup import BackupManager
from src.samba.linux_backend import LinuxHostSambaBackend
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.auth_page import create_auth_page
from src.ui.backup.backup_page import create_backup_page
from src.ui.storage.storage_page import create_storage_page
from src.ui.shares.shares_page import create_shares_page
from src.ui.dashboard_page import create_dashboard_page


def ensure_supported_runtime() -> None:
    """
    Refuse to start outside a Linux host that has Samba tooling available.
    """
    if os.name != "posix":
        raise RuntimeError(
            "Samba-Nice-WebUI requires a Linux host. "
            "Run it with Docker instead of starting Python directly."
        )

    if shutil.which("testparm") is None:
        raise RuntimeError(
            "The 'testparm' binary is required. "
            "Run the official Docker image or install samba-common-bin."
        )


# 1. Fail fast instead of silently degrading to a simulated backend
ensure_supported_runtime()

# 2. Initialize core system managers
backup_manager = BackupManager(
    backup_dir=settings.samba_backup_dir,
    include_conf_path=settings.samba_include_conf_path,
)

backend = LinuxHostSambaBackend(
    include_conf_path=settings.samba_include_conf_path,
    pid_file=settings.samba_pid_file,
    backup_manager=backup_manager,
)
dir_manager = StorageDirectoryManager(settings.parsed_storage_roots, backend=backend)


# 3. Register application page routes
@ui.page("/login")
def login_route():
    create_auth_page()


@ui.page("/")
def dashboard_route():
    create_dashboard_page(backend)


@ui.page("/shares")
def shares_route():
    create_shares_page(backend, dir_manager)


@ui.page("/storage")
def storage_route():
    create_storage_page(backend, dir_manager)


@ui.page("/backups")
def backups_route():
    create_backup_page(backend, backup_manager)


# 4. Main execution entry point
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host=settings.webui_host,
        port=settings.webui_port,
        title="Samba-Nice-WebUI",
        storage_secret=settings.webui_secret_key,
        reload=settings.webui_auto_reload,
        show=False
    )
