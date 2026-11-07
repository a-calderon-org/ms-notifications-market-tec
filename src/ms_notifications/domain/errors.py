class InvalidEventError(ValueError):
    """Raised when an incoming integration event violates the contract."""


class UnsupportedEventVersionError(InvalidEventError):
    """Raised when the event type is known but its schema version is unsupported."""


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor cannot be decoded safely."""


class NotificationNotFoundError(LookupError):
    """Raised when a notification is not visible to the authenticated user."""

