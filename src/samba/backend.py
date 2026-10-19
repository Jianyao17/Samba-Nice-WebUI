from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.core.models import ServerStatus, ShareConfig, ValidationResult


class SambaBackend(ABC):
    """
    Abstract interface for Samba operations.

    Defines the contract for interacting with Samba services,
    including querying service status, managing shares in configuration
    files, validating syntax via testparm, and triggering service reload.
    """

    @abstractmethod
    def get_status(self) -> ServerStatus:
        """
        Query current health, master PID, and active shares count of the Samba daemon.
        """
        pass

    @abstractmethod
    def list_shares(self) -> list[ShareConfig]:
        """
        Retrieve all active share definitions managed by the backend.
        """
        pass

    @abstractmethod
    def get_share(self, name: str) -> Optional[ShareConfig]:
        """
        Retrieve a specific share configuration by its section name.
        """
        pass

    @abstractmethod
    def save_share(
        self,
        share: ShareConfig,
        original_name: Optional[str] = None,
    ) -> ValidationResult:
        """
        Create, update, or rename a share configuration atomically.

        When ``original_name`` is None a new share is created; duplicate names
        are rejected. When it is set, the existing section is replaced and may
        be renamed to ``share.name``, provided the new name is not already used
        by another share.
        """
        pass

    @abstractmethod
    def delete_share(self, name: str) -> bool:
        """
        Delete a share configuration by name, snapshot the state, and reload service.
        """
        pass

    @abstractmethod
    def validate_config(self, conf_file_path: Path) -> ValidationResult:
        """
        Validate the syntax of a configuration file using testparm.
        """
        pass

    @abstractmethod
    def reload_service(self) -> bool:
        """
        Signal the running Samba daemon (smbd) to reload its configuration.
        """
        pass
