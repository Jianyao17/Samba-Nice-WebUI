# linux-runtime-bundle Specification

## Purpose
Provide a self-contained Linux x86_64 release artifact so the WebUI can run on a Samba host without Python, pip, uv, or a compiler.

## Requirements

### Requirement: Self-contained Linux release bundle

The release process SHALL publish a Linux x86_64 archive containing a portable Python 3.12 runtime, all application dependencies, and the application itself. The archive SHALL run on a host without a system Python, pip, uv, or compiler.

#### Scenario: Install on a host without Python

- **WHEN** an administrator installs the release bundle on a supported x86_64 host that has no Python interpreter installed
- **THEN** the application starts and serves the login page without installing Python or build tools

#### Scenario: Unsupported architecture

- **WHEN** the release bundle is extracted on a non-x86_64 host
- **THEN** the application fails with a clear architecture error instead of running with incompatible binaries

### Requirement: Stable runtime entrypoint

The bundle SHALL expose a stable executable entrypoint at `/opt/samba-nice-webui/venv/bin/samba-nice-webui` and SHALL start the same HTTP service that `python -m src.main` starts.

#### Scenario: Start through the bundle entrypoint

- **WHEN** the entrypoint runs with valid configuration
- **THEN** the WebUI listens on the configured host and port and serves the login page at `/login`

### Requirement: Release integrity metadata

Every published bundle SHALL have a SHA256 checksum and a version identifier. The checksum SHALL cover the exact archive that the installer downloads.

#### Scenario: Checksum matches

- **WHEN** the installer downloads a release archive and its matching checksum
- **THEN** the installer proceeds only if the computed SHA256 matches the published value

#### Scenario: Checksum mismatch

- **WHEN** the downloaded archive does not match the published checksum
- **THEN** the installer stops, deletes the archive, and leaves the installed version unchanged

### Requirement: Read-only runtime

The bundle SHALL run with its installation directory mounted read-only. Runtime writes SHALL be limited to the managed Samba directory and configured storage roots.

#### Scenario: Protect application files

- **WHEN** the service runs from `/opt/samba-nice-webui` with the application directory read-only
- **THEN** the application starts successfully and does not attempt to write bytecode, caches, or state into the installation directory

### Requirement: Supported host compatibility

The bundle SHALL run on Debian 12 or newer and Ubuntu 22.04 or newer on x86_64. The bundle SHALL NOT require newer glibc symbols than those releases provide.

#### Scenario: Run on the oldest supported Ubuntu release

- **WHEN** the bundle is installed on a clean Ubuntu 22.04 x86_64 host
- **THEN** the service starts and reports a running WebUI without a missing shared-library error
