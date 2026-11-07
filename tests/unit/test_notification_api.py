from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ms_notifications.api.main import create_app
from ms_notifications.application.ports import AuthenticatedPrincipal, AuthenticationError
from ms_notifications.config import Settings
from ms_notifications.domain.models import Notification
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository

USER_A_EVENT_1 = "11111111-1111-4111-8111-111111111111"
USER_A_EVENT_2 = "22222222-2222-4222-8222-222222222222"
USER_B_EVENT = "33333333-3333-4333-8333-333333333333"


class FakeAuthenticator:
    def authenticate(self, authorization):
        principals = {
            "Bearer user-a": AuthenticatedPrincipal(
                user_id="user-a",
                permissions=frozenset({"notifications:read", "notifications:write"}),
            ),
            "Bearer user-b": AuthenticatedPrincipal(
                user_id="user-b",
                permissions=frozenset({"notifications:read", "notifications:write"}),
            ),
            "Bearer read-only": AuthenticatedPrincipal(
                user_id="user-a",
                permissions=frozenset({"notifications:read"}),
            ),
            "Bearer no-access": AuthenticatedPrincipal(
                user_id="user-a",
                permissions=frozenset(),
            ),
        }
        try:
            return principals[authorization]
        except KeyError as exc:
            raise AuthenticationError("invalid test token") from exc


def notification(event_id, recipient, created_at, is_read=False):
    return Notification(
        event_id=event_id,
        recipient_user_id=recipient,
        sender_user_id="sender",
        chat_id="chat",
        message_id=f"message-{event_id[:4]}",
        occurred_at=int(created_at.timestamp()),
        correlation_id=f"correlation-{event_id[:4]}",
        created_at=created_at,
        is_read=is_read,
    )


def seeded_repository():
    repository = InMemoryNotificationRepository()
    repository.save_if_absent(
        notification(USER_A_EVENT_1, "user-a", datetime(2026, 11, 7, 12, 0, tzinfo=UTC))
    )
    repository.save_if_absent(
        notification(USER_A_EVENT_2, "user-a", datetime(2026, 11, 6, 12, 0, tzinfo=UTC))
    )
    repository.save_if_absent(
        notification(USER_B_EVENT, "user-b", datetime(2026, 11, 8, 12, 0, tzinfo=UTC))
    )
    return repository


def build_app(repository=None, authenticator=None):
    return create_app(
        Settings(notifications_repository="memory"),
        repository=repository or seeded_repository(),
        authenticator=authenticator or FakeAuthenticator(),
    )


def test_protected_endpoint_rejects_missing_and_invalid_credentials():
    with TestClient(build_app()) as client:
        missing = client.get("/v1/notifications")
        invalid = client.get(
            "/v1/notifications", headers={"Authorization": "Bearer invalid"}
        )

    for response in (missing, invalid):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["x-correlation-id"]


def test_permissions_produce_403_when_principal_lacks_access():
    with TestClient(build_app()) as client:
        response = client.get(
            "/v1/notifications", headers={"Authorization": "Bearer no-access"}
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_history_is_isolated_and_uses_stable_cursor_pagination():
    headers = {
        "Authorization": "Bearer user-a",
        "X-Correlation-ID": "request-history-001",
    }
    with TestClient(build_app()) as client:
        first = client.get("/v1/notifications?pageSize=1", headers=headers)
        cursor = first.json()["nextCursor"]
        second = client.get(
            "/v1/notifications",
            params={"pageSize": 1, "cursor": cursor},
            headers=headers,
        )

    assert first.status_code == 200
    assert first.headers["x-correlation-id"] == "request-history-001"
    assert [item["eventId"] for item in first.json()["items"]] == [USER_A_EVENT_1]
    assert "recipientUserId" not in first.json()["items"][0]
    assert first.json()["items"][0]["createdAt"] == 1794052800
    assert [item["eventId"] for item in second.json()["items"]] == [USER_A_EVENT_2]
    assert second.json()["nextCursor"] is None
    assert USER_B_EVENT not in str(first.json()) + str(second.json())


def test_page_size_invalid_cursor_and_invalid_correlation_return_400():
    headers = {"Authorization": "Bearer user-a"}
    with TestClient(build_app()) as client:
        too_small = client.get("/v1/notifications?pageSize=0", headers=headers)
        too_large = client.get("/v1/notifications?pageSize=101", headers=headers)
        bad_cursor = client.get("/v1/notifications?cursor=not-a-cursor", headers=headers)
        bad_correlation = client.get(
            "/v1/notifications",
            headers={**headers, "X-Correlation-ID": "not allowed spaces"},
        )

    assert too_small.status_code == 400
    assert too_large.status_code == 400
    assert too_small.json()["error"]["code"] == "VALIDATION_ERROR"
    assert too_large.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"]["code"] == "INVALID_CURSOR"
    assert bad_correlation.status_code == 400
    assert bad_correlation.json()["error"]["code"] == "INVALID_CORRELATION_ID"


def test_mark_read_is_idempotent():
    repository = seeded_repository()
    headers = {"Authorization": "Bearer user-a"}
    path = f"/v1/notifications/{USER_A_EVENT_1}/read"

    with TestClient(build_app(repository=repository)) as client:
        first = client.patch(path, headers=headers)
        second = client.patch(path, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["isRead"] is True
    assert second.json()["isRead"] is True


def test_user_cannot_read_or_modify_another_users_notification():
    repository = seeded_repository()
    headers = {"Authorization": "Bearer user-a"}

    with TestClient(build_app(repository=repository)) as client:
        response = client.patch(
            f"/v1/notifications/{USER_B_EVENT}/read",
            headers=headers,
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    user_b_notifications = repository.list_by_recipient("user-b", limit=10)
    assert len(user_b_notifications) == 1
    assert user_b_notifications[0].is_read is False


def test_mark_read_requires_write_permission_and_valid_uuid():
    with TestClient(build_app()) as client:
        forbidden = client.patch(
            f"/v1/notifications/{USER_A_EVENT_1}/read",
            headers={"Authorization": "Bearer read-only"},
        )
        invalid_id = client.patch(
            "/v1/notifications/not-a-uuid/read",
            headers={"Authorization": "Bearer user-a"},
        )

    assert forbidden.status_code == 403
    assert invalid_id.status_code == 400
    assert invalid_id.json()["error"]["code"] == "VALIDATION_ERROR"


def test_default_application_never_accepts_fake_tokens():
    app = create_app(Settings(notifications_repository="memory"))

    with TestClient(app) as client:
        response = client.get(
            "/v1/notifications",
            headers={"Authorization": "Bearer user-a"},
        )

    assert response.status_code == 401
