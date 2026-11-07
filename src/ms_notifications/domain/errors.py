class InvalidEventError(ValueError):
    """Raised when an incoming integration event violates the contract."""


class UnsupportedEventVersionError(InvalidEventError):
    """Raised when the event type is known but its schema version is unsupported."""

