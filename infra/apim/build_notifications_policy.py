"""Render the APIM API-scope policy for ms-notifications from a reviewed public JWKS.

The JWT checks mirror ``JWTAuthenticator`` in the backend and the shared
``market_tec/infra/apim/build_jwt_policy.py`` profile (RS256, ``at+jwt``, sub/sid/jti,
TTL <= 240 s). The script never fetches keys from the network or deploys to Azure.
"""
import argparse
import base64
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

PUBLIC_OPERATIONS = ("getLiveness", "getReadiness")
GATEWAY_HEADER = "X-MTEC-Notifications-Gateway-Key"
UNTRUSTED_HEADERS = (
    "X-User-Id",
    "X-Session-Id",
    "X-Authenticated-User",
    "X-MTEC-Authorization",
    "X-MTEC-Google-Authorization",
    "Cookie",
    "X-CSRF-Token",
)
MAX_TTL_SECONDS = 240


def _signing_keys(jwks: dict) -> list[dict]:
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 16:
        raise ValueError("invalid public key set")
    seen: set[str] = set()
    for key in keys:
        if not isinstance(key, dict) or set(key) != {"kty", "use", "alg", "kid", "n", "e"}:
            raise ValueError("unexpected or private JWK field")
        kid = key["kid"]
        if (key["kty"], key["use"], key["alg"]) != ("RSA", "sig", "RS256"):
            raise ValueError("only RSA/sig/RS256 keys are accepted")
        if not isinstance(kid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", kid) or kid in seen:
            raise ValueError("invalid or duplicate kid")
        seen.add(kid)
        for part in ("n", "e"):
            if not isinstance(key[part], str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key[part]):
                raise ValueError("invalid RSA value")
        modulus = int.from_bytes(base64.urlsafe_b64decode(key["n"] + "=="), "big")
        exponent = int.from_bytes(base64.urlsafe_b64decode(key["e"] + "=="), "big")
        if not 2048 <= modulus.bit_length() <= 8192 or exponent < 65537 or exponent % 2 != 1:
            raise ValueError("invalid RSA key strength")
    return keys


def build(jwks: dict, issuer: str, audience: str,
          gateway_named_value: str = "notifications-backend-key") -> str:
    if not re.fullmatch(r"https://[^\s<>\"]{1,248}", issuer):
        raise ValueError("invalid issuer")
    if not re.fullmatch(r"[A-Za-z0-9:._/-]{1,256}", audience):
        raise ValueError("invalid audience")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", gateway_named_value):
        raise ValueError("invalid gateway named value")
    keys = _signing_keys(jwks)

    root = ET.Element("policies")
    inbound = ET.SubElement(root, "inbound")
    ET.SubElement(inbound, "base")
    # Identity and gateway headers are never accepted from the client.
    for name in (*UNTRUSTED_HEADERS, GATEWAY_HEADER):
        ET.SubElement(inbound, "set-header", name=name, **{"exists-action": "delete"})

    public = " && ".join(f'context.Operation.Id != "{op}"' for op in PUBLIC_OPERATIONS)
    protected = ET.SubElement(ET.SubElement(inbound, "choose"), "when", condition=f"@({public})")
    check = ET.SubElement(protected, "validate-jwt", **{
        "header-name": "Authorization", "require-scheme": "Bearer",
        "require-signed-tokens": "true", "require-expiration-time": "true",
        "clock-skew": "0", "failed-validation-httpcode": "401",
        "failed-validation-error-message": "Invalid internal token",
        "output-token-variable-name": "internalJwt"})
    signing = ET.SubElement(check, "issuer-signing-keys")
    for key in keys:
        ET.SubElement(signing, "key", id=key["kid"], n=key["n"], e=key["e"])
    ET.SubElement(ET.SubElement(check, "audiences"), "audience").text = audience
    ET.SubElement(ET.SubElement(check, "issuers"), "issuer").text = issuer

    profile = ET.SubElement(ET.SubElement(protected, "choose"), "when", condition=(
        '@{ var jwt = (Jwt)context.Variables["internalJwt"]; '
        'return jwt.Algorithm != "RS256" || jwt.Type != "at+jwt" '
        "|| String.IsNullOrEmpty(jwt.Subject) || String.IsNullOrEmpty(jwt.Id) "
        "|| !jwt.IssuedAt.HasValue || !jwt.ExpirationTime.HasValue "
        f"|| (jwt.ExpirationTime.Value - jwt.IssuedAt.Value).TotalSeconds > {MAX_TTL_SECONDS} "
        '|| !jwt.Claims.ContainsKey("sid") || jwt.Claims["sid"].Length != 1 '
        '|| String.IsNullOrEmpty(jwt.Claims["sid"][0]); }'))
    denied = ET.SubElement(profile, "return-response")
    ET.SubElement(denied, "set-status", code="401", reason="Unauthorized")
    ET.SubElement(denied, "set-header", name="Content-Type",
                  **{"exists-action": "override"}).append(_value("application/json"))
    ET.SubElement(denied, "set-body").text = (
        '{"error":{"code":"INVALID_TOKEN","message":"Invalid internal token"}}')

    gateway = ET.SubElement(inbound, "set-header", name=GATEWAY_HEADER,
                            **{"exists-action": "override"})
    gateway.append(_value("{{" + gateway_named_value + "}}"))

    ET.SubElement(root, "backend").append(ET.Element("base"))
    outbound = ET.SubElement(root, "outbound")
    ET.SubElement(outbound, "base")
    ET.SubElement(outbound, "set-header", name="Cache-Control",
                  **{"exists-action": "override"}).append(_value("no-store"))
    ET.SubElement(outbound, "set-header", name="X-Content-Type-Options",
                  **{"exists-action": "override"}).append(_value("nosniff"))
    ET.SubElement(root, "on-error").append(ET.Element("base"))
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


def _value(text: str) -> ET.Element:
    element = ET.Element("value")
    element.text = text
    return element


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jwks", type=Path, required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--gateway-named-value", default="notifications-backend-key")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = build(json.loads(args.jwks.read_text(encoding="utf-8")), args.issuer,
                   args.audience, args.gateway_named_value)
    args.output.write_text(policy, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
