"""Project-scoped exception hierarchy."""


class CQUNetAuthError(Exception):
    """Base exception for this project."""


class PortalClientError(CQUNetAuthError):
    """Raised for portal client transport or protocol failures."""


class NotificationError(CQUNetAuthError):
    """Raised for notification delivery failures."""
