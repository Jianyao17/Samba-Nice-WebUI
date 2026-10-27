# Spec Delta

## Purpose

Enables administrators to manage Samba user accounts through the WebUI without
shell access, covering account creation, password management, and account lifecycle.

## ADDED Requirements

### Requirement: List Samba users
The system SHALL list all Samba users known to the host (via `pdbedit -L`), showing
username (normalized to lowercase), account status (enabled/disabled), and group memberships.

#### Scenario: Users exist
- **WHEN** the administrator opens the Users page
- **THEN** all Samba users are listed with their usernames and account status

#### Scenario: No users exist
- **WHEN** no Samba users have been created
- **THEN** the Users page shows an empty state with a prompt to add the first user

### Requirement: Create Samba user
The system SHALL create a new Samba user by (1) normalizing the username to lowercase,
(2) adding a no-login Unix account (`useradd -M -s /sbin/nologin`), and (3) registering
the user with Samba (`smbpasswd -a`). Passwords SHALL be passed via stdin to prevent
process inspection. The system SHALL reject usernames that conflict with pre-existing
Unix or Samba users.

#### Scenario: Valid new user
- **WHEN** the administrator submits a new username and password
- **THEN** a nologin Unix account is created with lowercase username and the user is registered with Samba
- **AND** the user appears in the user list as enabled

#### Scenario: Username normalization
- **WHEN** the administrator submits an uppercase or mixed-case username (e.g. `Alice`)
- **THEN** the username is automatically normalized to lowercase (`alice`) before validation and creation

#### Scenario: Username already exists in /etc/passwd
- **WHEN** the submitted username matches a pre-existing Unix account
- **THEN** the system rejects the request and reports a conflict error
- **AND** no modification is made to any user account

#### Scenario: Username contains invalid characters
- **WHEN** the submitted username contains characters outside `[a-z0-9_.-]` or
  starts with a digit or hyphen
- **THEN** the system rejects the request with a validation error before invoking
  any system command

### Requirement: Change Samba password
The system SHALL update the Samba password for an existing user via `smbpasswd -s`,
feeding the password via stdin with UTF-8 encoding. It SHALL NOT modify the Unix
account password in `/etc/shadow`.

#### Scenario: Successful password change
- **WHEN** the administrator submits a new password for an existing user
- **THEN** the Samba password is updated
- **AND** the user can authenticate to Samba shares with the new password

#### Scenario: Password with special characters
- **WHEN** the administrator submits a password containing spaces, non-ASCII UTF-8 characters, or shell symbols
- **THEN** the password is transmitted securely via stdin and applied without shell-escaping errors

#### Scenario: User does not exist
- **WHEN** the target username is not a known Samba user
- **THEN** the system returns an error without modifying any account

### Requirement: Enable and disable Samba user
The system SHALL enable or disable a Samba user's ability to authenticate via SMB
using `smbpasswd -e` (enable) and `smbpasswd -d` (disable), followed by signaling
the Samba daemon to reload so updated state takes effect. It SHALL NOT alter the
underlying Unix account.

#### Scenario: Disable active user
- **WHEN** the administrator disables an enabled user
- **THEN** the user can no longer authenticate to Samba shares
- **AND** the Unix account and Samba user record remain intact

#### Scenario: Enable disabled user
- **WHEN** the administrator enables a previously disabled user
- **THEN** the user can again authenticate to Samba shares using the existing password

### Requirement: Delete Samba user
The system SHALL remove a Samba user by (1) checking share references, (2) removing
the Samba account (`smbpasswd -x`), and (3) removing the Unix account (`userdel`).
It SHALL NOT delete any storage data. It SHALL refuse deletion if the user is
referenced in any active share's `valid users` or `write list`.

#### Scenario: Delete unreferenced user
- **WHEN** the administrator confirms deletion of a user not referenced in any active share
- **THEN** the Samba account and nologin Unix account are removed
- **AND** the user no longer appears in the user list

#### Scenario: Refuse to delete user referenced in active shares
- **WHEN** the administrator attempts to delete a user that is listed in `valid users`
  or `write list` of one or more active shares (matching comma- or space-separated tokens case-insensitively)
- **THEN** the system rejects deletion, reports the conflicting share names, and makes no change to any account

#### Scenario: Refuse to delete non-Samba-managed user
- **WHEN** the target Unix account was not created by the WebUI (e.g. `root`,
  `nobody`, `www-data`, or any account whose shell is not `/sbin/nologin`)
- **THEN** the system refuses deletion and reports a protection error

### Requirement: Safe user operations under concurrency
The system SHALL validate that a target username exists (for update/delete) or is
absent (for create) immediately before invoking any system command, and SHALL report
a race-condition error if the state has changed since the page was loaded.

#### Scenario: User removed between list and delete
- **WHEN** another process deletes a user between the list fetch and the delete action
- **THEN** the system reports that the user no longer exists without crashing
