from abc import ABC, abstractmethod

from src.core.models import SambaGroup, SambaUser, UserOperationResult


class SambaUserBackend(ABC):
    """
    Abstract interface for Samba user and group operations.

    Mirrors ``SambaBackend`` so callers can depend on a small, testable
    contract instead of a concrete Linux implementation.
    """

    @abstractmethod
    def list_users(self) -> list[SambaUser]:
        """
        List every Samba account known to the host.
        """
        pass

    @abstractmethod
    def create_user(self, username: str, password: str) -> UserOperationResult:
        """
        Create a no-login Unix account and register it with Samba.
        """
        pass

    @abstractmethod
    def set_password(self, username: str, password: str) -> UserOperationResult:
        """
        Replace the Samba password of an existing user.
        """
        pass

    @abstractmethod
    def enable_user(self, username: str) -> UserOperationResult:
        """
        Allow an existing Samba user to authenticate again.
        """
        pass

    @abstractmethod
    def disable_user(self, username: str) -> UserOperationResult:
        """
        Block an existing Samba user from authenticating.
        """
        pass

    @abstractmethod
    def delete_user(self, username: str) -> UserOperationResult:
        """
        Remove a Samba account and its no-login Unix account.
        """
        pass

    @abstractmethod
    def list_groups(self) -> list[SambaGroup]:
        """
        List Unix groups that are usable as Samba share principals.
        """
        pass

    @abstractmethod
    def create_group(self, name: str) -> UserOperationResult:
        """
        Create a Unix group for use as a Samba share principal.
        """
        pass

    @abstractmethod
    def add_user_to_group(self, username: str, group: str) -> UserOperationResult:
        """
        Add a Samba-managed user to a group.
        """
        pass

    @abstractmethod
    def remove_user_from_group(self, username: str, group: str) -> UserOperationResult:
        """
        Remove a user from a group.
        """
        pass

    @abstractmethod
    def delete_group(self, name: str) -> UserOperationResult:
        """
        Delete an unused group that is not referenced by any share.
        """
        pass
