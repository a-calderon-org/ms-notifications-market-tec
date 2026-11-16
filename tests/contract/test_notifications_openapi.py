import json
from pathlib import Path

from ms_notifications.api.main import create_app
from ms_notifications.config import Settings

CONTRACT_PATH = Path("contracts/openapi/notifications.json")


def test_notifications_contract_is_valid_json_and_matches_routes():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    generated = create_app(Settings(notifications_repository="memory")).openapi()

    assert contract["openapi"] == "3.0.3"
    assert contract["info"]["version"] == "0.4.0-draft"
    assert contract["servers"][0]["url"] == "https://markettec-api.azure-api.net/notifications"
    for path in ("/health/live", "/health/ready"):
        assert path in generated["paths"]
        assert contract["paths"][path]["get"]["security"] == []
    assert "/v1/notifications" in generated["paths"]
    assert "/v1/notifications/stream" in generated["paths"]
    assert "/v1/notifications/{notificationId}/read" in generated["paths"]
    assert "get" in contract["paths"]["/v1/notifications"]
    assert "patch" in contract["paths"]["/v1/notifications/{notificationId}/read"]


def test_contract_documents_required_status_codes_and_security():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    list_operation = contract["paths"]["/v1/notifications"]["get"]
    mark_operation = contract["paths"]["/v1/notifications/{notificationId}/read"]["patch"]
    stream_operation = contract["paths"]["/v1/notifications/stream"]["get"]

    assert set(list_operation["responses"]) == {"200", "400", "401", "403"}
    assert set(mark_operation["responses"]) == {"200", "400", "401", "403", "404"}
    assert set(stream_operation["responses"]) == {"200", "400", "401", "403", "429"}
    assert list_operation["security"] == [{"bearerAuth": []}]
    assert mark_operation["security"] == [{"bearerAuth": []}]
    assert stream_operation["security"] == [{"bearerAuth": []}]
    assert stream_operation["parameters"][1] == {"$ref": "#/components/parameters/LastEventId"}
