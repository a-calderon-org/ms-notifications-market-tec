from fastapi.testclient import TestClient

from ms_notifications.api.main import create_app
from ms_notifications.application.ports import AuthenticatedPrincipal, AuthenticationError
from ms_notifications.config import Settings
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository


class StreamAuthenticator:
    def authenticate(self, authorization):
        if authorization == "Bearer reader":
            return AuthenticatedPrincipal(
                user_id="user-a",
                permissions=frozenset({"notifications:read"}),
            )
        if authorization == "Bearer forbidden":
            return AuthenticatedPrincipal(user_id="user-a", permissions=frozenset())
        raise AuthenticationError("invalid token")


def build_app():
    return create_app(
        Settings(notifications_repository="memory"),
        repository=InMemoryNotificationRepository(),
        authenticator=StreamAuthenticator(),
    )


def test_stream_rejects_missing_authentication_and_permission():
    with TestClient(build_app()) as client:
        missing = client.get("/v1/notifications/stream")
        forbidden = client.get(
            "/v1/notifications/stream",
            headers={"Authorization": "Bearer forbidden"},
        )

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "UNAUTHENTICATED"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


def test_stream_rejects_malformed_last_event_id_before_opening_connection():
    with TestClient(build_app()) as client:
        response = client.get(
            "/v1/notifications/stream",
            headers={
                "Authorization": "Bearer reader",
                "Last-Event-ID": "not-a-uuid",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
