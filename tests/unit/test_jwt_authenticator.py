import json
from time import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ms_notifications.application.ports import AuthenticationError
from ms_notifications.infrastructure.auth import JWTAuthenticator

ISSUER = "https://markettec-api.azure-api.net/users-prod"
AUDIENCE = "markettec-api"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()


class StaticSigningKey:
    def __init__(self) -> None:
        self.key = PUBLIC_KEY


class StaticSigningKeyProvider:
    def get_signing_key_from_jwt(self, token: str) -> StaticSigningKey:
        del token
        return StaticSigningKey()


def authenticator() -> JWTAuthenticator:
    return JWTAuthenticator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://identity.example.test/.well-known/jwks.json",
        signing_key_provider=StaticSigningKeyProvider(),
    )


def token(
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    ttl: int = 240,
    issued_at: int | None = None,
    include_scope: bool = True,
    headers: dict | None = None,
    **overrides,
) -> str:
    now = int(time()) if issued_at is None else issued_at
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": "user-recipient",
        "sid": "session-123",
        "jti": "token-123",
        "iat": now,
        "exp": now + ttl,
        **overrides,
    }
    if include_scope:
        claims.setdefault("scope", "notifications:read notifications:write")
    return jwt.encode(
        claims,
        PRIVATE_KEY,
        algorithm="RS256",
        headers=(
            {"kid": "prod-jwt-2026-11", "typ": "at+jwt"}
            if headers is None
            else headers
        ),
    )


def test_valid_internal_token_builds_recipient_scoped_principal():
    principal = authenticator().authenticate(f"Bearer {token()}")

    assert principal.user_id == "user-recipient"
    assert principal.permissions == frozenset(
        {"notifications:read", "notifications:write"}
    )


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer", "Bearer ", "Bearer one two"],
)
def test_malformed_authorization_is_rejected(authorization):
    with pytest.raises(AuthenticationError):
        authenticator().authenticate(authorization)


@pytest.mark.parametrize(
    "encoded",
    [
        lambda: token(issuer="https://wrong.example"),
        lambda: token(audience="wrong-audience"),
        lambda: token(issued_at=int(time()) - 300, ttl=1),
        lambda: token(ttl=241),
        lambda: token(headers={"kid": "prod-jwt-2026-11", "typ": "JWT"}),
        lambda: token(headers={"typ": "at+jwt"}),
        lambda: token(sub=""),
        lambda: token(sid=""),
        lambda: token(jti=""),
    ],
)
def test_invalid_contract_tokens_are_rejected(encoded):
    with pytest.raises(AuthenticationError):
        authenticator().authenticate(f"Bearer {encoded()}")


def test_absent_scopes_authenticates_without_granting_permissions():
    encoded = token(include_scope=False)

    principal = authenticator().authenticate(f"Bearer {encoded}")

    assert principal.permissions == frozenset()


def test_list_and_space_separated_scope_claims_are_combined():
    encoded = token(
        scope="notifications:read",
        scp=["notifications:write"],
        scopes=["notifications:stream"],
    )

    principal = authenticator().authenticate(f"Bearer {encoded}")

    assert principal.permissions == frozenset(
        {"notifications:read", "notifications:write", "notifications:stream"}
    )


def test_explicit_default_permissions_support_current_scope_less_tokens():
    verifier = JWTAuthenticator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://identity.example.test/.well-known/jwks.json",
        default_permissions=frozenset({"notifications:read", "notifications:write"}),
        signing_key_provider=StaticSigningKeyProvider(),
    )

    principal = verifier.authenticate(f"Bearer {token(include_scope=False)}")

    assert principal.permissions == frozenset(
        {"notifications:read", "notifications:write"}
    )


def test_reviewed_static_public_jwks_can_validate_tokens():
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(PUBLIC_KEY, as_dict=True)
    public_jwk.update({"kid": "prod-jwt-2026-11", "alg": "RS256", "use": "sig"})
    verifier = JWTAuthenticator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_json=json.dumps({"keys": [public_jwk]}),
    )

    principal = verifier.authenticate(f"Bearer {token()}")

    assert principal.user_id == "user-recipient"


def test_static_jwks_rejects_private_material_and_duplicate_kids():
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(PUBLIC_KEY, as_dict=True)
    public_jwk.update({"kid": "duplicate", "alg": "RS256", "use": "sig"})
    private_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(PRIVATE_KEY, as_dict=True)
    private_jwk.update({"kid": "private", "alg": "RS256", "use": "sig"})

    with pytest.raises(ValueError, match="private key"):
        JWTAuthenticator(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_json=json.dumps({"keys": [private_jwk]}),
        )
    with pytest.raises(ValueError, match="unique"):
        JWTAuthenticator(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_json=json.dumps({"keys": [public_jwk, public_jwk]}),
        )


def test_jwks_url_must_be_https():
    with pytest.raises(ValueError, match="HTTPS"):
        JWTAuthenticator(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_url="http://identity.example.test/jwks.json",
        )
