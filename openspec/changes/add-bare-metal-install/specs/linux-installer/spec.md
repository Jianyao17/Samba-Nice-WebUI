# Spec Delta

## Purpose

Install, configure, update, and remove the WebUI as a hardened systemd service on supported bare-metal Linux hosts.

## ADDED Requirements

### Requirement: Supported host preflight

The installer SHALL require Linux on x86_64, root privileges, systemd, and an apt-based Debian 12/13 or Ubuntu 22.04/24.04 host. It SHALL refuse unsupported hosts before modifying the system and SHALL report the unmet condition.

#### Scenario: Unsupported distribution

- **WHEN** the installer runs on a host outside the supported Debian/Ubuntu set
- **THEN** it exits non-zero, names the unsupported distribution, and changes no files

#### Scenario: Missing root privileges

- **WHEN** the installer runs without root privileges
- **THEN** it exits non-zero and instructs the administrator to run it with sudo, without changing any files

### Requirement: Host dependency provisioning

On a supported host, the installer SHALL ensure `smbd`, `testparm`, `curl`, `tar`, and `openssl` are available. It SHALL install missing Samba packages with apt and SHALL NOT install or require Python, pip, uv, or a compiler.

#### Scenario: Samba is missing

- **WHEN** `smbd` or `testparm` is not installed on a supported host
- **THEN** the installer installs the Samba server and common tools packages and verifies `testparm` is available

#### Scenario: Samba is already installed

- **WHEN** Samba and `testparm` are already present
- **THEN** the installer leaves the existing Samba installation in place and does not remove or replace `smb.conf`

### Requirement: Safe install and update

The installer SHALL download and verify the requested x86_64 bundle before stopping the running service. It SHALL install into `/opt/samba-nice-webui` and preserve `/etc/samba-nice-webui/webui.env`, `/etc/samba/smb.webui.conf`, `/etc/samba/.backups`, and the storage-roots drop-in. If download, verification, extraction, or replacement fails, the previously installed version SHALL remain runnable.

#### Scenario: Fresh installation

- **WHEN** the installer runs on a clean supported host
- **THEN** the service starts with the requested release version and serves the WebUI

#### Scenario: Update preserves state

- **WHEN** the installer runs again with a newer release version
- **THEN** the application is replaced, the existing environment file and backup history are preserved, and the service runs the new version

#### Scenario: Failed download leaves the old version running

- **WHEN** the release archive cannot be downloaded or its checksum does not match
- **THEN** the installer exits non-zero, keeps the previous installation and service state, and does not replace any application files

### Requirement: Interactive first-run configuration

On first install, when a terminal is available and `--non-interactive` is not set, the installer SHALL ask exactly three questions: admin username, admin password, and allowed storage roots. Defaults SHALL be `admin` for the username, a generated password when the answer is blank, and `/mnt` for the allowed storage roots. The password prompt SHALL not echo input. Answers SHALL be accepted from `--admin-user`, `--admin-password`, and `--allowed-roots`, in which case the corresponding question is skipped. If no terminal is available, the installer SHALL proceed with the supplied flags and defaults without prompting. The installer SHALL never prompt during `--dry-run`, `--uninstall`, or an update of an existing installation.

#### Scenario: Defaults on first install

- **WHEN** the installer asks the three first-run questions on a terminal and the administrator accepts each default
- **THEN** the environment file contains the username `admin`, a generated password, and `/mnt` as the allowed storage root

#### Scenario: Custom answers

- **WHEN** the administrator enters a username, a password, and `/mnt/data, /mnt/media`
- **THEN** the environment file uses those values and the service can write to both roots

#### Scenario: Flags skip the prompts

- **WHEN** `--admin-user`, `--admin-password`, and `--allowed-roots` are all supplied
- **THEN** the installer does not ask any first-run question

#### Scenario: No terminal available

- **WHEN** the installer runs through `curl | bash` or another pipe without a controlling terminal
- **THEN** it does not hang waiting for input, applies the supplied flags, and prints the generated or default values it used

#### Scenario: Invalid storage root

- **WHEN** an entered or supplied storage root is not an absolute path, is `/`, or overlaps `/etc/samba`
- **THEN** the installer rejects it with a clear message before writing any configuration

### Requirement: Generated configuration

On first install, the installer SHALL create `/etc/samba-nice-webui/webui.env` with mode `0600`, containing the chosen admin username and password, a generated session secret, `/etc/samba/smb.webui.conf`, `/etc/samba/.backups`, `/run/samba/smbd.pid`, and the chosen allowed storage roots with `/mnt` as the default. It SHALL NOT overwrite an existing environment file, except that `--allowed-roots` SHALL replace only the `ALLOWED_STORAGE_ROOTS` line after backing up the file. It SHALL print the access URL and the effective credentials once.

#### Scenario: First install creates configuration

- **WHEN** no environment file exists
- **THEN** the installer writes a new mode `0600` environment file with the chosen credentials and the documented paths

#### Scenario: Re-run preserves configuration

- **WHEN** the installer runs again and the environment file already exists
- **THEN** the existing password, session secret, and path values remain unchanged and no first-run question is asked

#### Scenario: Storage roots are changed through the installer

- **WHEN** the installer runs again with `--allowed-roots /mnt/data,/mnt/media`
- **THEN** it backs up the environment file, replaces the `ALLOWED_STORAGE_ROOTS` line with those roots, updates the storage-roots drop-in, restarts the service, and leaves every other setting unchanged

#### Scenario: Storage roots are created

- **WHEN** a configured storage root does not exist yet
- **THEN** the installer creates it before starting the service, and does not modify an existing directory

#### Scenario: Credentials are reported

- **WHEN** installation completes successfully
- **THEN** the installer prints the WebUI URL, admin username, and admin password

### Requirement: Hardened systemd service

The installer SHALL install, enable, and start `samba-nice-webui.service`. The unit SHALL run as root with `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `NoNewPrivileges=yes`, `UMask=0022`, and `ReadWritePaths=/etc/samba`. Because `ProtectSystem=strict` makes every other path read-only, the installer SHALL also write `/etc/systemd/system/samba-nice-webui.service.d/10-storage-roots.conf` granting write access to each configured storage root, and SHALL preserve that drop-in across updates. The unit SHALL restart on failure and log to journald. The installer SHALL verify the service becomes active and SHALL report recent logs on failure.

#### Scenario: Service becomes active

- **WHEN** installation finishes
- **THEN** `systemctl is-active samba-nice-webui` reports `active`

#### Scenario: Storage roots remain writable

- **WHEN** a storage root other than `/etc/samba` is configured
- **THEN** the service can create folders under it while the rest of the filesystem stays read-only for the service

#### Scenario: Service fails to start

- **WHEN** the service exits during startup
- **THEN** the installer exits non-zero and prints recent journal entries for the service

#### Scenario: Service starts after reboot

- **WHEN** the host reboots after a successful installation
- **THEN** systemd starts the WebUI service automatically

### Requirement: Samba include bootstrap

By default, the installer SHALL add `include = /etc/samba/smb.webui.conf` as the last directive of the `[global]` section of `/etc/samba/smb.conf`. It SHALL back up `smb.conf` before editing, SHALL NOT add a duplicate include, SHALL validate the full configuration with `testparm`, and SHALL restore the backup and fail if validation fails. `--no-samba-config` SHALL skip this step. After a successful change, it SHALL reload `smbd` when running.

#### Scenario: Add the include directive

- **WHEN** `smb.conf` has a `[global]` section without the managed include and `--no-samba-config` is not set
- **THEN** the installer backs up `smb.conf`, adds the include as the last directive of `[global]`, validates it, and reloads Samba

#### Scenario: Include already present

- **WHEN** `smb.conf` already contains the managed include directive
- **THEN** the installer does not add another copy and still validates the configuration

#### Scenario: Validation fails

- **WHEN** `testparm` rejects the edited configuration
- **THEN** the installer restores the backup, exits non-zero, and does not reload Samba

#### Scenario: Samba configuration is skipped

- **WHEN** the installer runs with `--no-samba-config`
- **THEN** `smb.conf` remains byte-for-byte unchanged

### Requirement: Uninstall and purge

`--uninstall` SHALL stop and disable the service, remove the unit and `/opt/samba-nice-webui`, and preserve `/etc/samba-nice-webui`, `/etc/samba/smb.webui.conf`, `/etc/samba/.backups`, the storage-roots drop-in, and configured storage data. `--purge` SHALL additionally remove installer-managed configuration, backups, the drop-in, and the managed include file, and SHALL remove the include line from `smb.conf` after backing it up. Samba itself SHALL remain installed, and no storage directory SHALL be deleted.

#### Scenario: Uninstall preserves Samba data

- **WHEN** the installer runs with `--uninstall`
- **THEN** the service and application are removed while the environment file, managed include file, backups, and shared storage remain

#### Scenario: Purge removes managed state

- **WHEN** the installer runs with `--uninstall --purge`
- **THEN** the managed include line and installer-created configuration and backups are removed, and `smb.conf` is backed up before the include line is removed

#### Scenario: Samba remains installed

- **WHEN** uninstall completes
- **THEN** Samba packages, `smbd`, and any shares that remain in `smb.conf` still work

### Requirement: Non-interactive and dry-run operation

The installer SHALL support non-interactive execution and SHALL accept `--version`, `--admin-user`, `--admin-password`, `--allowed-roots`, `--non-interactive`, `--no-samba-config`, `--uninstall`, `--purge`, and `--dry-run`. `--dry-run` SHALL print planned changes without modifying the system and without prompting. An unknown version, an invalid value, or an unsupported flag SHALL fail before changing the system.

#### Scenario: Dry run changes nothing

- **WHEN** the installer runs with `--dry-run`
- **THEN** it prints the planned actions, asks no questions, and leaves files, packages, and services unchanged

#### Scenario: Non-interactive install

- **WHEN** the installer runs with `--non-interactive` and all required choices supplied as flags
- **THEN** it completes without prompting and applies the requested configuration

#### Scenario: Invalid version

- **WHEN** the requested release version does not exist
- **THEN** the installer exits non-zero before stopping the service or modifying files
