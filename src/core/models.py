from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class ShareConfig(BaseModel):
    """
    Data model representing a Samba share configuration block.

    Encapsulates standard Samba INI parameters such as section name,
    filesystem path, access mode (read-only/writable), browseability,
    guest access flags, and access control lists.
    """

    # 1. Share identifier and filesystem target path
    name: str = Field(..., min_length=1, max_length=64, description="Samba share name (bracket section name)")
    path: str = Field(..., min_length=1, description="Absolute filesystem target path")

    # 2. General metadata and permissions
    comment: str = Field(default="", description="Descriptive share comment")
    read_only: bool = Field(default=False, description="Whether the share is read-only")
    browsable: bool = Field(default=True, description="Whether the share appears in network browse lists")
    guest_ok: bool = Field(default=False, description="Whether guest/anonymous access is permitted")

    # 3. Access control lists
    valid_users: str = Field(default="", description="Optional comma/space-separated list of allowed users")
    write_list: str = Field(default="", description="Optional comma/space-separated list of write-permitted users")

    # 4. Custom key-value parameters for advanced settings
    extra_options: dict[str, str] = Field(default_factory=dict, description="Custom Samba share options")

    # 5. Metadata for config origin
    conf_file: Optional[str] = Field(default=None, description="Path or filename where this share is stored")


class ValidationResult(BaseModel):
    """
    Represents the output and status of configuration syntax validation (via testparm).
    """

    # 1. Boolean indicating syntax correctness
    is_valid: bool

    # 2. Detailed stdout or stderr from testparm validation
    message: str


class ServerStatus(BaseModel):
    """
    Represents the runtime operational state of the Samba service daemon (smbd).
    """

    # 1. Host Samba daemon status
    is_running: bool
    pid: Optional[int] = None

    # 2. Aggregate metrics
    shares_count: int = 0
    uptime_description: str = "Unknown"
    last_reloaded_at: Optional[datetime] = None


class BackupSnapshot(BaseModel):
    """
    Metadata describing an individual timestamped configuration backup snapshot.
    """

    # 1. Unique snapshot identifier and timestamp
    snapshot_id: str
    created_at: datetime
    description: str

    # 2. Files contained in this snapshot
    files: list[str] = Field(default_factory=list)

    # 3. SHA-256 of the backed-up configuration file (empty for legacy snapshots)
    file_hash: str = Field(default="", description="SHA-256 hash of the backed-up configuration file")
