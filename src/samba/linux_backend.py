import os
import signal
import subprocess
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


class LinuxHostSambaBackend(SambaBackend):
    """
    Production Samba backend for Linux hosts.

    Interacts directly with host Linux filesystem mounts and daemons:
    - Writes shares to a dedicated include configuration file (e.g. smb.webui.conf).
    - Validates configuration using local 'testparm' binary without invoking a shell.
    - Sends SIGHUP to the smbd daemon PID to achieve zero-downtime configuration reloads.
    - Captures timestamped backups prior to applying modifications.
    """

    def __init__(
        self,
        include_conf_path: Path,
        pid_file: Path,
        backup_manager: BackupManager,
    ):
        # 1. Initialize file references and backup manager
        self.pid_file = pid_file
        self.include_conf_path = include_conf_path
        self.backup_manager = backup_manager
        self.last_reloaded_at: Optional[datetime] = None

        self.include_conf_path.parent.mkdir(parents=True, exist_ok=True)

    def get_status(self) -> ServerStatus:
        # 1. Check if the PID file exists
        if not self.pid_file.exists():
            return ServerStatus(
                is_running=False,
                shares_count=len(self.list_shares()),
                last_reloaded_at=self.last_reloaded_at
            )

        try:
            # 2. Read PID and check if process is currently alive
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)
            is_running = True
        except (ValueError, ProcessLookupError, PermissionError):
            is_running = False
            pid = None

        # 3. Return aggregated daemon status
        return ServerStatus(
            is_running=is_running,
            pid=pid,
            shares_count=len(self.list_shares()),
            last_reloaded_at=self.last_reloaded_at
        )

    def list_shares(self) -> list[ShareConfig]:
        # 1. Parse all shares contained in the dedicated include file
        if not self.include_conf_path.exists():
            return []

        return parse_conf_file(self.include_conf_path)

    def get_share(self, name: str) -> Optional[ShareConfig]:
        # 1. Locate specific share configuration by name
        clean_name = name.strip().lower()
        for share in self.list_shares():
            if share.name.lower() == clean_name:
                return share

        return None

    def validate_config(self, conf_file_path: Path) -> ValidationResult:
        # 1. Run in-container testparm binary without invoking shell
        try:
            result = subprocess.run(
                ["testparm", "-s", str(conf_file_path)],
                capture_output=True,
                text=True,
                check=False
            )

            is_valid = result.returncode == 0
            message = result.stdout if is_valid else result.stderr
            return ValidationResult(is_valid=is_valid, message=message.strip())

        except FileNotFoundError:
            return ValidationResult(
                is_valid=False,
                message="Binary 'testparm' not found. Ensure samba-client is installed in container."
            )

    def save_share(self, share: ShareConfig) -> ValidationResult:
        # 1. Sanitize share name
        clean_name = sanitize_share_name(share.name)
        share.conf_file = self.include_conf_path.name
        share.name = clean_name

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

        # 3. Write entire updated configuration to temporary file
        temp_file = self.include_conf_path.with_name(f".tmp_{self.include_conf_path.name}")
        temp_file.write_text(serialize_all_shares(updated_shares), encoding="utf-8")

        # 4. Validate configuration syntax via testparm
        val_result = self.validate_config(temp_file)
        if not val_result.is_valid:
            if temp_file.exists():
                temp_file.unlink()
            return val_result

        # 5. Snapshot backup before committing changes
        self.backup_manager.create_snapshot(f"Before saving share '{clean_name}'")

        # 6. Atomically replace dedicated include configuration file
        temp_file.replace(self.include_conf_path)

        # 7. Signal host daemon reload
        self.reload_service()

        return ValidationResult(
            is_valid=True,
            message=f"Share '{clean_name}' saved to {self.include_conf_path.name} and applied."
        )

    def delete_share(self, name: str) -> bool:
        # 1. Sanitize requested share name
        clean_name = sanitize_share_name(name)
        current_shares = self.list_shares()

        remaining_shares = [s for s in current_shares if s.name.lower() != clean_name.lower()]
        if len(remaining_shares) == len(current_shares):
            return False

        # 2. Snapshot current configuration before deletion
        self.backup_manager.create_snapshot(f"Before deleting share '{clean_name}'")

        # 3. Write remaining shares back to the include file atomically
        temp_file = self.include_conf_path.with_name(f".tmp_{self.include_conf_path.name}")
        temp_file.write_text(serialize_all_shares(remaining_shares), encoding="utf-8")
        temp_file.replace(self.include_conf_path)

        # 4. Signal host daemon reload
        self.reload_service()
        return True

    def reload_service(self) -> bool:
        # 1. Verify existence of the PID file
        if not self.pid_file.exists():
            return False

        try:
            # 2. Read master smbd PID
            pid = int(self.pid_file.read_text().strip())

            # 3. Send SIGHUP to trigger zero-downtime configuration reload
            os.kill(pid, signal.SIGHUP)
            self.last_reloaded_at = datetime.now()
            return True

        except (ValueError, ProcessLookupError, PermissionError):
            return False
