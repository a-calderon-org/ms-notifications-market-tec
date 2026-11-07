from ms_notifications.application.ports import AuthenticatedPrincipal, AuthenticationError


class RejectAllAuthenticator:
    """Safe default until the shared JWT/APIM contract is approved and implemented."""

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        del authorization
        raise AuthenticationError("authentication is not configured")
