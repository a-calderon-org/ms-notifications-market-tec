from fastapi.testclient import TestClient

from ms_notifications.api.main import create_app
from ms_notifications.config import Settings


def test_health_endpoints():
    app = create_app(Settings(notifications_repository="memory"))

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        ready = client.get("/health/ready")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "repository": "memory"}

