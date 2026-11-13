import json
from collections.abc import Mapping
from typing import Any, Protocol

import jwt
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError

from ms_notifications.application.ports import AuthenticatedPrincipal, AuthenticationError
from ms_notifications.config import Settings


class RejectAllAuthenticator:
    """Safe default until the shared JWT/APIM contract is approved and implemented."""

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        del authorization
        raise AuthenticationError("authentication is not configured")


class SigningKeyProvider(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any:
        """Return a trusted signing key selected from the configured JWKS."""


class StaticJWKSetProvider:
    """Select public RSA signing keys from a reviewed, provisioned JWKS snapshot."""

    _PRIVATE_JWK_FIELDS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})

    def __init__(self, jwks_json: str) -> None:
        try:
            document = json.loads(jwks_json)
        except json.JSONDecodeError as exc:
            raise ValueError("JWT_JWKS_JSON must be valid JSON") from exc
        keys = document.get("keys") if isinstance(document, dict) else None
        if not isinstance(keys, list) or not keys:
            raise ValueError("JWT_JWKS_JSON must contain a non-empty keys array")

        self._keys: dict[str, Any] = {}
        for value in keys:
            if not isinstance(value, dict):
                raise ValueError("each JWK must be an object")
            if self._PRIVATE_JWK_FIELDS.intersection(value):
                raise ValueError("JWT_JWKS_JSON must not contain private key material")
            kid = value.get("kid")
            if not isinstance(kid, str) or not kid or kid in self._keys:
                raise ValueError("every JWK must have a unique non-empty kid")
            if value.get("kty") != "RSA" or value.get("alg") != "RS256":
                raise ValueError("only RSA/RS256 JWKs are accepted")
            if value.get("use") not in (None, "sig"):
                raise ValueError("JWK use must be sig")
            self._keys[kid] = jwt.PyJWK.from_dict(value, algorithm="RS256")

    def get_signing_key_from_jwt(self, token: str) -> Any:
        kid = jwt.get_unverified_header(token).get("kid")
        try:
            return self._keys[kid]
        except (KeyError, TypeError) as exc:
            raise PyJWKClientError("JWT kid is not present in the provisioned JWKS") from exc


class JWTAuthenticator:
    """Validate the internal MarketTec access-token profile defensively."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str = "",
        jwks_json: str = "",
        default_permissions: frozenset[str] = frozenset(),
        max_ttl_seconds: int = 240,
        jwks_timeout_seconds: int = 5,
        jwks_cache_seconds: int = 300,
        signing_key_provider: SigningKeyProvider | None = None,
    ) -> None:
        if not issuer or not audience:
            raise ValueError("JWT_ISSUER and JWT_AUDIENCE are required")
        self._issuer = issuer
        self._audience = audience
        self._max_ttl_seconds = max_ttl_seconds
        self._default_permissions = default_permissions
        if signing_key_provider is not None:
            self._signing_keys = signing_key_provider
        elif bool(jwks_url) == bool(jwks_json):
            raise ValueError("configure exactly one of JWT_JWKS_URL or JWT_JWKS_JSON")
        elif jwks_url:
            if not jwks_url.startswith("https://"):
                raise ValueError("JWT_JWKS_URL must use HTTPS")
            self._signing_keys = PyJWKClient(
                jwks_url,
                cache_jwk_set=True,
                lifespan=jwks_cache_seconds,
                cache_keys=True,
                timeout=jwks_timeout_seconds,
            )
        else:
            self._signing_keys = StaticJWKSetProvider(jwks_json)

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        token = self._bearer_token(authorization)
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise AuthenticationError("unexpected JWT algorithm")
            if header.get("typ") != "at+jwt":
                raise AuthenticationError("unexpected JWT type")
            if not isinstance(header.get("kid"), str) or not header["kid"]:
                raise AuthenticationError("JWT kid is required")

            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=0,
                options={
                    "require": ["iss", "aud", "sub", "sid", "iat", "exp", "jti"],
                    "strict_aud": True,
                },
            )
            self._validate_contract_claims(claims)
        except AuthenticationError:
            raise
        except (InvalidTokenError, PyJWKClientError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("invalid access token") from exc

        return AuthenticatedPrincipal(
            user_id=claims["sub"],
            permissions=self._default_permissions.union(self._permissions(claims)),
        )

    @staticmethod
    def _bearer_token(authorization: str | None) -> str:
        if authorization is None:
            raise AuthenticationError("Bearer token is required")
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token or " " in token:
            raise AuthenticationError("Bearer token is malformed")
        return token

    def _validate_contract_claims(self, claims: Mapping[str, Any]) -> None:
        for claim in ("sub", "sid", "jti"):
            value = claims.get(claim)
            if not isinstance(value, str) or not value.strip():
                raise AuthenticationError(f"JWT {claim} must be a non-empty string")
        if len(claims["sub"]) > 64:
            raise AuthenticationError("JWT sub exceeds the UserId contract")

        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            raise AuthenticationError("JWT iat must be an integer NumericDate")
        if isinstance(expires_at, bool) or not isinstance(expires_at, int):
            raise AuthenticationError("JWT exp must be an integer NumericDate")
        ttl = expires_at - issued_at
        if ttl <= 0 or ttl > self._max_ttl_seconds:
            raise AuthenticationError("JWT lifetime violates the access-token contract")
        not_before = claims.get("nbf")
        if not_before is not None and (
            isinstance(not_before, bool) or not isinstance(not_before, int)
        ):
            raise AuthenticationError("JWT nbf must be an integer NumericDate")

    @staticmethod
    def _permissions(claims: Mapping[str, Any]) -> frozenset[str]:
        permissions: set[str] = set()
        for name in ("scope", "scp", "scopes"):
            value = claims.get(name)
            if isinstance(value, str):
                permissions.update(part for part in value.split() if part)
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                permissions.update(item for item in value if item)
            elif value is not None:
                raise AuthenticationError(f"JWT {name} has an invalid type")
        return frozenset(permissions)


def build_authenticator(settings: Settings):
    if settings.authentication_mode == "jwt":
        return JWTAuthenticator(
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            jwks_url=settings.jwt_jwks_url,
            jwks_json=settings.jwt_jwks_json,
            default_permissions=frozenset(settings.jwt_default_permissions.split()),
            max_ttl_seconds=settings.jwt_max_ttl_seconds,
            jwks_timeout_seconds=settings.jwt_jwks_timeout_seconds,
            jwks_cache_seconds=settings.jwt_jwks_cache_seconds,
        )
    return RejectAllAuthenticator()
