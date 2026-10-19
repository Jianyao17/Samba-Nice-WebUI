import json
from pathlib import Path
from typing import Any, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration schema loaded from environment variables and .env file.

    Provides centralized, typed settings for WebUI network bindings, authentication
    credentials, the dedicated Samba include file path, and allowed storage boundary directories.

    The primary smb.conf is never read or written by this application — only the dedicated
    include file (SAMBA_INCLUDE_CONF_PATH) is managed. This keeps the scope minimal and safe.
    """

    # 1. WebUI server credentials and network bindings
    webui_host: str = "0.0.0.0"
    webui_port: int = 8080
    webui_admin_user: str = "admin"
    webui_admin_password: str = "adminpassword"
    webui_secret_key: str = "change-this-secret-key-in-production"
    webui_auto_reload: bool = False

    # 2. Samba paths — only the dedicated include file is managed by this app.
    #    The primary smb.conf is NEVER read or written; the user must add one
    #    'include = <path>' directive to it pointing at this file.
    samba_include_conf_path: Path = Path("/etc/samba/smb.webui.conf")
    samba_backup_dir: Path = Path("/etc/samba/.backups")
    samba_pid_file: Path = Path("/var/run/samba/smbd.pid")

    # 3. Allowed directory roots (accepts raw string or list)
    allowed_storage_roots: Union[str, list[str]] = "/storage"
    samba_backend: str = "linux"

    # 4. Settings configuration loader from .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def parsed_storage_roots(self) -> list[str]:
        # 1. Parse comma-separated or list configuration into clean list of strings
        v = self.allowed_storage_roots
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                try:
                    return json.loads(v_str)
                except json.JSONDecodeError:
                    pass
            return [part.strip() for part in v_str.split(",") if part.strip()]

        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]

        return ["/storage"]


settings = Settings()
