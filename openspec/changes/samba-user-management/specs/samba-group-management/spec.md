# Spec Delta

## Purpose

Enables administrators to manage Unix groups used as Samba share principals,
so that shares can be granted to groups (`@groupname`) rather than individual users.

## ADDED Requirements

### Requirement: List groups
The system SHALL list all Unix groups that contain at least one Samba-managed user,
showing the group name (normalized to lowercase), GID, and member list.

#### Scenario: Groups exist
- **WHEN** the administrator opens the Groups section of the Users page
- **THEN** all groups containing Samba users are listed with their names and members

#### Scenario: No groups exist
- **WHEN** no groups have been created
- **THEN** an empty state with a prompt to add the first group is shown

### Requirement: Create group
The system SHALL create a new Unix group via `groupadd` after normalizing the group
name to lowercase. It SHALL reject group names that conflict with any pre-existing
Unix group.

#### Scenario: Valid new group
- **WHEN** the administrator submits a new group name
- **THEN** the group is created with lowercase name and appears in the group list

#### Scenario: Group name normalization
- **WHEN** the administrator enters mixed or uppercase characters (e.g. `Developers`)
- **THEN** the group name is converted to lowercase (`developers`) before creation

#### Scenario: Group name already exists
- **WHEN** the submitted group name matches a pre-existing Unix group
- **THEN** the system rejects the request with a conflict error
- **AND** no modification is made to the group database

#### Scenario: Invalid group name
- **WHEN** the group name contains characters outside `[a-z0-9_.-]` or starts with
  a digit or hyphen
- **THEN** the system rejects the request with a validation error before invoking
  any system command

### Requirement: Assign and remove group members
The system SHALL add a Samba user to a group via `usermod -aG` and remove a user
from a group via `gpasswd -d`. It SHALL only operate on users that are
Samba-managed (nologin accounts created by the WebUI).

#### Scenario: Add user to group
- **WHEN** the administrator assigns an existing Samba user to a group
- **THEN** the user appears in the group's member list
- **AND** the group becomes usable as `@groupname` in share ACLs

#### Scenario: Remove user from group
- **WHEN** the administrator removes a user from a group
- **THEN** the user no longer appears in that group's member list

#### Scenario: Target is not a Samba-managed user
- **WHEN** the administrator tries to add a non-Samba-managed system user to a group
- **THEN** the system rejects the operation with an error

### Requirement: Delete group
The system SHALL delete an empty Unix group via `groupdel`. It SHALL refuse to delete
a group that still has members, a group referenced in any active share, or a system group.

#### Scenario: Delete empty group
- **WHEN** the administrator deletes a group with no members that is not referenced by any share
- **THEN** the group is removed from the system

#### Scenario: Refuse to delete non-empty group
- **WHEN** the target group still has members
- **THEN** the system rejects the deletion with an error listing the member usernames

#### Scenario: Refuse to delete group referenced in active shares
- **WHEN** the administrator attempts to delete a group that is listed as `@groupname`
  in `valid users` or `write list` of one or more active shares (matching comma- or space-separated tokens case-insensitively)
- **THEN** the system rejects deletion, reports the conflicting share names, and makes no change to the group database

#### Scenario: Refuse to delete system group
- **WHEN** the target group name matches a pre-existing non-WebUI group (e.g. `root`,
  `sudo`, `www-data`, or GID < 1000)
- **THEN** the system refuses deletion and reports a protection error
