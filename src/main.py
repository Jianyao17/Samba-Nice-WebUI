import logging
import os
import shutil

from nicegui import app, ui

from src.config import settings
from src.core.backup import BackupManager
from src.samba.linux_backend import LinuxHostSambaBackend
from src.samba.linux_user_backend import LinuxSambaUserBackend
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.auth_page import create_auth_page
from src.ui.backup.backup_page import create_backup_page
from src.ui.storage.storage_page import create_storage_page
from src.ui.shares.shares_page import create_shares_page
from src.ui.dashboard_page import create_dashboard_page
from src.ui.users.users_page import create_users_page


logger = logging.getLogger(__name__)


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

dir_manager = StorageDirectoryManager(
    settings.parsed_storage_roots, 
    backend=backend
)

user_backend = LinuxSambaUserBackend(samba_backend=backend)
for binary in ("smbpasswd", "pdbedit", "useradd", "groupadd"):
    if shutil.which(binary) is None:
        logger.warning(
            "Optional user-management binary '%s' is missing; "
            "user and group management will be unavailable.",
            binary,
        )


# 3. Register application page routes
@ui.page("/login")
def login_route():
    create_auth_page()


@ui.page("/")
def dashboard_route():
    create_dashboard_page(backend)


@ui.page("/shares")
def shares_route():
    create_shares_page(backend, dir_manager, user_backend)


@ui.page("/storage")
def storage_route():
    create_storage_page(backend, dir_manager)


@ui.page("/users")
def users_route():
    create_users_page(user_backend, backend)


@ui.page("/backups")
def backups_route():
    create_backup_page(backend, backup_manager)


## Add shared CSS to keep floating labels clear of outlined input borders.
ui.add_css("""
/* Floating labels that overlap the top border of all outlined inputs */
.q-field--outlined.q-field--labeled.q-field--float .q-field__label {
    top: 0;
    z-index: 1;
    padding: 0 5px;
    background-color: var(--q-field-bg, white);
    transform: translateY(-30%) scale(0.75);
}

/* Adjust the content position when the label floats */
.q-field--outlined.q-field--labeled.q-field--float
.q-field__control-container {
    padding-top: 8px;
}

.q-field--outlined.q-field--labeled.q-field--float
.q-field__native,
.q-field--outlined.q-field--labeled.q-field--float
.q-field__input {
    padding-top: 0;
}
""", shared=True)


# 4. Main execution entry point
def main() -> None:
    """
    Start the NiceGUI web server.
    """
    ui.run(
        host=settings.webui_host,
        port=settings.webui_port,
        title="Samba-Nice-WebUI",
        storage_secret=settings.webui_secret_key,
        reload=settings.webui_auto_reload,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()

