from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.backup import BackupManager
from src.core.models import ServerStatus, ShareConfig, ValidationResult
from src.samba.backend import SambaBackend
from src.samba.parser import (
    parse_conf_file,
    sanitize_share_name,
    serialize_all_shares,
)


class MockSambaBackend(SambaBackend):
    """
    Simulated Samba backend for offline local development and automated testing.

    Permits testing the full WebUI lifecycle on non-Linux platforms (e.g. Windows)
    without requiring root permissions, Docker, or native Samba binaries.
    Simulates validation, daemon status, and zero-downtime service reloads.
    """

    def __init__(
        self,
        include_conf_path: Path,
        pid_file: Path,
        backup_manager: BackupManager,
    ):
        # 1. Initialize file references and backup manager
        self.include_conf_path = include_conf_path
        self.pid_file = pid_file
        self.backup_manager = backup_manager
        self.last_reloaded_at: Optional[datetime] = datetime.now()

        self.include_conf_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Seed initial demo share in the include file if not present
        self._ensure_sample_data()

    def _ensure_sample_data(self):
        # 1. Create initial sample share if the include file does not exist
        if not self.include_conf_path.exists():
            sample_share = ShareConfig(
                name="public",
                path="/storage/public",
                comment="Public Storage (Mock)",
                read_only=False,
                browsable=True,
                guest_ok=True,
                conf_file=self.include_conf_path.name
            )
            self.include_conf_path.write_text(serialize_all_shares([sample_share]), encoding="utf-8")

    def get_status(self) -> ServerStatus:
        # 1. Return mock active server status
        return ServerStatus(
            is_running=True,
            pid=1234,
            shares_count=len(self.list_shares()),
            uptime_description="Mock Samba Service (Single Include Conf)",
            last_reloaded_at=self.last_reloaded_at
        )

    def list_shares(self) -> list[ShareConfig]:
        # 1. Parse all shares contained in the dedicated include file
        if not self.include_conf_path.exists():
            return []

        return parse_conf_file(self.include_conf_path)

    def get_share(self, name: str) -> Optional[ShareConfig]:
        # 1. Find share by name
        clean_name = name.strip().lower()
        for share in self.list_shares():
            if share.name.lower() == clean_name:
                return share

        return None

    def validate_config(self, conf_file_path: Path) -> ValidationResult:
        # 1. Validate that the configuration file can be parsed correctly
        try:
            shares = parse_conf_file(conf_file_path)
            if not shares:
                return ValidationResult(is_valid=False, message="No valid share sections found in file.")

            for s in shares:
                if not s.path.strip():
                    return ValidationResult(is_valid=False, message=f"Share '{s.name}' is missing path.")

            return ValidationResult(is_valid=True, message="Syntax mock validation passed successfully.")

        except Exception as exc:
            return ValidationResult(is_valid=False, message=f"Parse error: {str(exc)}")

    def save_share(self, share: ShareConfig) -> ValidationResult:
        # 1. Sanitize share name
        clean_name = sanitize_share_name(share.name)
        share.name = clean_name
        share.conf_file = self.include_conf_path.name

        # 2. Update existing share list or append new share
        current_shares = self.list_shares()
        updated_shares: list[ShareConfig] = []
        found = False

        for s in current_shares:
            if s.name.lower() == clean_name.lower():
                updated_shares.append(share)
                found = True
            else:
                updated_shares.append(s)

        if not found:
            updated_shares.append(share)

        # 3. Write updated shares to temp file and mock-validate
        temp_file = self.include_conf_path.with_name(f".tmp_{self.include_conf_path.name}")
        temp_file.write_text(serialize_all_shares(updated_shares), encoding="utf-8")

        val = self.validate_config(temp_file)
        if not val.is_valid:
            if temp_file.exists():
                temp_file.unlink()
            return val

        # 4. Snapshot the current state before committing
        self.backup_manager.create_snapshot(f"Configuration before saving share '{clean_name}'")
        temp_file.replace(self.include_conf_path)

        # 5. Update simulated reload timestamp and record the resulting configuration
        self.reload_service()
        self.backup_manager.create_snapshot(f"Saved share '{clean_name}'")

        return ValidationResult(
            is_valid=True,
            message=f"Share '{clean_name}' saved to {self.include_conf_path.name} (Mock)."
        )

    def delete_share(self, name: str) -> bool:
        # 1. Sanitize requested share name
        clean_name = sanitize_share_name(name)
        current_shares = self.list_shares()

        remaining_shares = [s for s in current_shares if s.name.lower() != clean_name.lower()]
        if len(remaining_shares) == len(current_shares):
            return False

        # 2. Snapshot the current state before deletion
        self.backup_manager.create_snapshot(f"Configuration before deleting share '{clean_name}'")

        # 3. Write remaining shares back to the include file atomically
        temp_file = self.include_conf_path.with_name(f".tmp_{self.include_conf_path.name}")
        temp_file.write_text(serialize_all_shares(remaining_shares), encoding="utf-8")
        temp_file.replace(self.include_conf_path)

        # 4. Update simulated reload timestamp and record the resulting configuration
        self.reload_service()
        self.backup_manager.create_snapshot(f"Deleted share '{clean_name}'")
        return True

    def reload_service(self) -> bool:
        # 1. Simulate reload timestamp update
        self.last_reloaded_at = datetime.now()
        return True
