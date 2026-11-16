# APIM: publicación y seguridad de ms-notifications

Policy como código para el API `markettec-notifications-api` (sufijo `notifications`)
en el APIM compartido `markettec-api` (nivel Consumption, West US 2).

| Archivo | Propósito |
|---|---|
| [`build_notifications_policy.py`](build_notifications_policy.py) | Genera la policy desde un JWKS público revisado. No consulta la red ni despliega nada. |
| [`notifications-api-policy.xml`](notifications-api-policy.xml) | Policy a nivel de API generada para producción (`users-prod`). La prueba `tests/contract/test_apim_policy.py` falla si queda desactualizada. |
| [`jwks/prod-jwt-2026-11.json`](jwks/prod-jwt-2026-11.json) | Clave pública RS256 de ms-users. Es la misma que `market_tec/infra/apim/production/jwks/` y que `JWT_JWKS_JSON` del App Service (kid `prod-jwt-2026-11`). |
| [`../../contracts/openapi/notifications.json`](../../contracts/openapi/notifications.json) | Contrato OpenAPI 3.0.3 que se importa en APIM (Swagger). |

## Controles de seguridad

Flujo: SPA → APIM → App Service. ms-users emite el JWT interno.

| # | Control | Dónde | Resultado si falla |
|---|---|---|---|
| 1 | TLS obligatorio | APIM (HTTPS) y App Service (`httpsOnly=true`) | Sin texto plano |
| 2 | `validate-jwt`: firma RS256 con clave fija, `iss=https://markettec-api.azure-api.net/users-prod`, `aud=markettec-api`, `exp` obligatorio, `clock-skew=0` | Policy APIM | `401` en el gateway |
| 3 | Perfil de token: `typ=at+jwt`, `sub`, `jti`, `sid`, `iat`, TTL ≤ 240 s | Policy APIM (`choose`) | `401 INVALID_TOKEN` |
| 4 | Se eliminan los headers de identidad o de gateway que envía el cliente (`X-User-Id`, `X-Authenticated-User`, `Cookie`, `X-MTEC-Notifications-Gateway-Key`, …) | Policy APIM | El cliente no puede suplantar identidad |
| 5 | APIM inyecta `X-MTEC-Notifications-Gateway-Key` desde el named value secreto `notifications-backend-key` | Policy APIM | — |
| 6 | El backend exige esa clave en todo excepto `/health/*` (comparación en tiempo constante) | `APIM_GATEWAY_KEY` en App Service | `403 DIRECT_ACCESS_FORBIDDEN` en acceso directo |
| 7 | Defensa en profundidad: el backend revalida el JWT completo | `JWTAuthenticator` (`AUTHENTICATION_MODE=jwt`) | `401 UNAUTHENTICATED` |
| 8 | Autorización: el destinatario sale solo de `sub`; permisos `notifications:read`/`write`; una notificación ajena responde igual que una inexistente | FastAPI | `403` / `404` |
| 9 | `Cache-Control: no-store` y `X-Content-Type-Options: nosniff` | Policy APIM (outbound) | — |
| 10 | Secretos en Key Vault con Managed Identity; ningún secreto en el repo ni en Postman | App Service + `kv-mtec-notif-dev` | — |

`/health/live` y `/health/ready` son públicos (operationId `getLiveness`/`getReadiness`)
y no exponen datos de usuario.

**Limitaciones conocidas**
- APIM Consumption no admite mTLS hacia el backend con certificado de cliente por API ni integración VNet. Por eso se usa la clave de gateway del patrón de ms-catalog.
- `rate-limit-by-key` no existe en Consumption, y `rate-limit` requiere suscripción. El API no exige subscription key porque la SPA lo llama directamente.
- Consumption no garantiza SSE de larga duración (ver [MTEC-26](../../docs/MTEC-26_REALTIME_SSE.md)).

## Regenerar la policy

```bash
python infra/apim/build_notifications_policy.py \
  --jwks infra/apim/jwks/prod-jwt-2026-11.json \
  --issuer https://markettec-api.azure-api.net/users-prod \
  --audience markettec-api \
  --output infra/apim/notifications-api-policy.xml
```

## Aplicar en Azure (en orden)

Requiere `az login` con acceso a la suscripción de `markettec-api` (grupo
`markettec-dev`) y a la de ms-notifications (grupo `rg-markettec-notifications-dev-cc`).
Ejecutar desde la raíz del repo en Git Bash.

```bash
APIM_SUB="<id de la suscripción de markettec-api>"
APIM_RG=markettec-dev; APIM=markettec-api; API=markettec-notifications-api
APP_RG=rg-markettec-notifications-dev-cc; APP=app-mtec-notifications-dev-cc; KV=kv-mtec-notif-dev
BACKEND=https://app-mtec-notifications-dev-cc-hpgpb4azbaexfxc3.canadacentral-01.azurewebsites.net
ARM="https://management.azure.com/subscriptions/$APIM_SUB/resourceGroups/$APIM_RG/providers/Microsoft.ApiManagement/service/$APIM"

# 0. Desplegar primero el backend con este cambio (Actions > Deploy development).
#    Con APIM_GATEWAY_KEY vacío, el comportamiento actual no cambia.

# 1. Importar el contrato: agrega stream y health a las 2 operaciones existentes.
az apim api import --subscription "$APIM_SUB" -g "$APIM_RG" -n "$APIM" \
  --api-id "$API" --path notifications --display-name "MarketTEC Notifications API" \
  --specification-format OpenApiJson --specification-path contracts/openapi/notifications.json \
  --service-url "$BACKEND" --protocols https --subscription-required false

# 2. Generar la clave de gateway una sola vez y guardarla en Key Vault (nunca en Git).
KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
az keyvault secret set --vault-name "$KV" -n apim-gateway-key --value "$KEY" -o none

# 3. Crear el named value secreto en APIM y aplicar la policy del API.
az apim nv create --subscription "$APIM_SUB" -g "$APIM_RG" -n "$APIM" \
  --named-value-id notifications-backend-key --display-name notifications-backend-key \
  --value "$KEY" --secret true -o none
python -c "import json; print(json.dumps({'properties': {'format': 'rawxml', 'value': open('infra/apim/notifications-api-policy.xml', encoding='utf-8').read()}}))" > /tmp/notif-policy.json
az rest --method put --url "$ARM/apis/$API/policies/policy?api-version=2022-08-01" --body @/tmp/notif-policy.json -o none
rm /tmp/notif-policy.json

# 4. Activar el bloqueo de acceso directo en el backend (referencia a Key Vault).
SECRET_URI=$(az keyvault secret show --vault-name "$KV" -n apim-gateway-key --query id -o tsv | sed 's#/[^/]*$##')
az webapp config appsettings set -g "$APP_RG" -n "$APP" \
  --settings "APIM_GATEWAY_KEY=@Microsoft.KeyVault(SecretUri=$SECRET_URI/)" -o none
unset KEY
```

Para revertir, borrar `APIM_GATEWAY_KEY` del App Service (paso 4) y después la policy
(`az rest --method delete` sobre la misma URL del paso 3).

## Verificación

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://markettec-api.azure-api.net/notifications/health/live      # 200
curl -s -o /dev/null -w "%{http_code}\n" https://markettec-api.azure-api.net/notifications/v1/notifications  # 401 (APIM)
curl -s "$BACKEND/v1/notifications"                                                                           # 403 DIRECT_ACCESS_FORBIDDEN
```

Después ejecutar la colección de Postman (ver [docs/ENTREGABLES_FASE2.md](../../docs/ENTREGABLES_FASE2.md)).
