import pytest
from fastapi.testclient import TestClient

from ms_notifications.api.main import GATEWAY_KEY_HEADER, create_app
from ms_notifications.application.ports import AuthenticatedPrincipal
from ms_notifications.config import Settings

GATEWAY_KEY = "k" * 43


class AllowAuthenticator:
    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        del authorization
        return AuthenticatedPrincipal(
            user_id="user-recipient",
            permissions=frozenset({"notifications:read", "notifications:write"}),
        )


def _client(gateway_key: str = GATEWAY_KEY) -> TestClient:
    settings = Settings(notifications_repository="memory", apim_gateway_key=gateway_key)
    return TestClient(create_app(settings, authenticator=AllowAuthenticator()))


def test_direct_request_without_gateway_key_is_forbidden():
    with _client() as client:
        response = client.get("/v1/notifications", headers={"X-Correlation-ID": "direct-1"})

    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "DIRECT_ACCESS_FORBIDDEN",
        "message": "Requests must be routed through the MarketTec API gateway",
        "correlationId": "direct-1",
    }
    assert response.headers["X-Correlation-ID"] == "direct-1"


def test_wrong_gateway_key_is_forbidden():
    with _client() as client:
        response = client.get("/v1/notifications", headers={GATEWAY_KEY_HEADER: "x" * 43})

    assert response.status_code == 403


def test_gateway_key_allows_request():
    with _client() as client:
        response = client.get("/v1/notifications", headers={GATEWAY_KEY_HEADER: GATEWAY_KEY})

    assert response.status_code == 200
    assert response.json() == {"items": [], "nextCursor": None}


def test_health_probes_stay_reachable_without_gateway_key():
    with _client() as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200


def test_openapi_docs_require_gateway_key_when_enabled():
    with _client() as client:
        assert client.get("/openapi.json").status_code == 403


def test_gate_is_disabled_when_key_is_empty():
    with _client(gateway_key="") as client:
        assert client.get("/v1/notifications").status_code == 200


def test_short_gateway_key_is_rejected_at_startup():
    with pytest.raises(ValueError, match="at least 32"):
        create_app(Settings(notifications_repository="memory", apim_gateway_key="short"))
