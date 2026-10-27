# Spec Delta

## MODIFIED Requirements

### Requirement: Host dependency provisioning
On a supported host, the installer SHALL ensure `smbd`, `testparm`, `smbpasswd`,
`pdbedit`, `useradd`, `groupadd`, `curl`, `tar`, and `openssl` are available.
It SHALL install missing Samba packages (`samba`, `samba-common-bin`) and the
`passwd` package with apt, and SHALL NOT install or require Python, pip, uv, or
a compiler.

#### Scenario: Samba is missing
- **WHEN** `smbd` or `testparm` is not installed on a supported host
- **THEN** the installer installs the Samba server and common tools packages and
  verifies `testparm` is available

#### Scenario: Samba is already installed
- **WHEN** Samba and `testparm` are already present
- **THEN** the installer leaves the existing Samba installation in place and does
  not remove or replace `smb.conf`

#### Scenario: smbpasswd is missing
- **WHEN** `smbpasswd` or `pdbedit` is not found after Samba package installation
- **THEN** the installer reports the missing binary and exits with a non-zero code
  before starting the service
