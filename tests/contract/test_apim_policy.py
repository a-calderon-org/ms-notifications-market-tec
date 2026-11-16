import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "infra" / "apim"))

from build_notifications_policy import GATEWAY_HEADER, build  # noqa: E402

JWKS = json.loads((ROOT / "infra/apim/jwks/prod-jwt-2026-11.json").read_text(encoding="utf-8"))
ISSUER = "https://markettec-api.azure-api.net/users-prod"
AUDIENCE = "markettec-api"


def _policy() -> ET.Element:
    return ET.fromstring(build(JWKS, ISSUER, AUDIENCE))


def test_committed_policy_matches_generator():
    committed = (ROOT / "infra/apim/notifications-api-policy.xml").read_text(encoding="utf-8")

    assert committed == build(JWKS, ISSUER, AUDIENCE)


def test_policy_validates_internal_jwt_profile():
    check = _policy().find("inbound/choose/when/validate-jwt")

    assert check is not None
    assert check.get("require-scheme") == "Bearer"
    assert check.get("require-signed-tokens") == "true"
    assert check.get("require-expiration-time") == "true"
    assert check.get("clock-skew") == "0"
    assert check.get("failed-validation-httpcode") == "401"
    assert check.findtext("audiences/audience") == AUDIENCE
    assert check.findtext("issuers/issuer") == ISSUER
    assert [key.get("id") for key in check.find("issuer-signing-keys")] == ["prod-jwt-2026-11"]
    profile = _policy().find("inbound/choose/when/choose/when").get("condition")
    for fragment in ('"at+jwt"', '"RS256"', "> 240", '"sid"', "jwt.Id", "jwt.Subject"):
        assert fragment in profile


def test_health_operations_are_the_only_ones_without_jwt():
    condition = _policy().find("inbound/choose/when").get("condition")

    assert condition == (
        '@(context.Operation.Id != "getLiveness" && context.Operation.Id != "getReadiness")'
    )


def test_client_identity_and_gateway_headers_are_deleted_before_injection():
    inbound = list(_policy().find("inbound"))
    deleted = [e.get("name") for e in inbound if e.get("exists-action") == "delete"]
    injected = [e for e in inbound if e.get("exists-action") == "override"]

    assert {"X-User-Id", "X-Authenticated-User", "Cookie", GATEWAY_HEADER} <= set(deleted)
    assert len(injected) == 1
    assert injected[0].get("name") == GATEWAY_HEADER
    assert injected[0].findtext("value") == "{{notifications-backend-key}}"
    assert inbound.index(injected[0]) == len(inbound) - 1


def test_responses_are_not_cached():
    outbound = _policy().find("outbound")
    headers = {e.get("name"): e.findtext("value") for e in outbound.findall("set-header")}

    assert headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "jwks",
    [
        {"keys": []},
        {"keys": [{**JWKS["keys"][0], "d": "private"}]},
        {"keys": [{**JWKS["keys"][0], "alg": "HS256"}]},
        {"keys": [JWKS["keys"][0], JWKS["keys"][0]]},
    ],
)
def test_rejects_unsafe_key_sets(jwks):
    with pytest.raises(ValueError):
        build(jwks, ISSUER, AUDIENCE)


def test_rejects_non_https_issuer():
    with pytest.raises(ValueError):
        build(JWKS, "http://markettec-api.azure-api.net/users-prod", AUDIENCE)
