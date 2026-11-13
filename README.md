# ms-notifications-market-tec

Microservicio de notificaciones de MarketTEC. La primera iteración cubre el
núcleo de **MTEC-22**: recibe eventos `message.sent.v1`, valida el contrato y
crea una sola notificación por `eventId`, aunque el evento sea reprocesado.

## Estado actual

- FastAPI y Python 3.12.
- Arquitectura hexagonal: dominio y aplicación no dependen de Azure.
- Persistencia en memoria para desarrollo inmediato.
- Adaptador MongoDB compatible con Azure Cosmos DB for MongoDB.
- Contrato JSON Schema provisional para `message.sent.v1`.
- Pruebas de procesamiento correcto, deduplicación y eventos inválidos.

> Los tickets de Jira mencionan Azure Table Storage para MTEC-23. Usar Cosmos
> DB for MongoDB es un cambio de arquitectura y debe aprobarse/documentarse
> antes de dar ese ticket por terminado.

## Requisitos

- Python 3.12 (la versión objetivo de Azure).
- Docker Desktop, opcional, para ejecutar MongoDB localmente.

## Inicio rápido sin base de datos

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m uvicorn ms_notifications.api.main:app --app-dir src --reload
```

Abrí:

- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`
- `http://localhost:8000/docs`

Los endpoints `/v1/notifications` están cerrados por defecto hasta integrar el
autenticador aprobado por MTEC-12/MTEC-15. El contrato y la guía de MTEC-25 están
en [`docs/MTEC-25_NOTIFICATIONS_API.md`](docs/MTEC-25_NOTIFICATIONS_API.md).

Para ejecutar las pruebas:

```powershell
python -m pytest
```

## Consumidor de Azure Queue

Con las variables de Azure Queue configuradas en `.env` y una sesión iniciada
con `az login`, instalá el proyecto en modo editable una sola vez:

```powershell
python -m pip install -e .
```

Después iniciá el consumidor en una terminal separada:

```powershell
ms-notifications-worker
```

El consumidor procesa `message-sent-v1`. Los mensajes inválidos pasan
inmediatamente a poison; los fallos transitorios se reintentan y pasan a
`message-sent-v1-poison` al quinto intento. La política completa y el replay
manual están en [`docs/MTEC-24_QUEUE_OPERATIONS.md`](docs/MTEC-24_QUEUE_OPERATIONS.md).

## Desarrollo con MongoDB local

```powershell
docker compose up -d mongo
$env:NOTIFICATIONS_REPOSITORY="mongo"
$env:MONGODB_URI="mongodb://localhost:27017"
python -m uvicorn ms_notifications.api.main:app --app-dir src --reload
```

No se debe subir un archivo `.env` ni una cadena de conexión real al
repositorio. En Azure, la configuración se inyectará mediante App Service y,
posteriormente, Key Vault/Managed Identity cuando corresponda.

## Variables de configuración

| Variable | Valor inicial | Uso |
|---|---|---|
| `NOTIFICATIONS_REPOSITORY` | `memory` | `memory` o `mongo` |
| `MONGODB_URI` | vacío | Cadena MongoDB/Cosmos; requerida con `mongo` |
| `MONGODB_DATABASE` | `market_tec_notifications` | Base de datos propia del microservicio |
| `MONGODB_COLLECTION` | `notifications` | Colección de notificaciones |
| `AZURE_STORAGE_QUEUE_ENDPOINT` | vacío | Endpoint del servicio Queue Storage |
| `AZURE_QUEUE_NAME` | `message-sent-v1` | Cola de entrada |
| `AZURE_POISON_QUEUE_NAME` | `message-sent-v1-poison` | Cola de fallos permanentes |
| `QUEUE_VISIBILITY_TIMEOUT_SECONDS` | `30` | Tiempo antes de reintentar un fallo |
| `QUEUE_MAX_DEQUEUE_COUNT` | `5` | Intentos antes de mover a poison |
| `QUEUE_POLL_INTERVAL_SECONDS` | `5` | Espera cuando no hay mensajes |
| `SSE_POLL_INTERVAL_SECONDS` | `2` | Frecuencia de consulta del stream |
| `SSE_HEARTBEAT_INTERVAL_SECONDS` | `15` | Intervalo de keep-alive SSE |
| `SSE_BATCH_SIZE` | `100` | Ventana máxima para reconexión |
| `SSE_MAX_CONNECTIONS` | `100` | Límite de streams por instancia |
| `SSE_MAX_CONNECTIONS_PER_USER` | `3` | Límite de streams por usuario |
| `SSE_MAX_CONNECTION_DURATION_SECONDS` | `300` | Tiempo antes de reautenticar |
| `LOG_LEVEL` | `INFO` | Nivel de logging |

## Autenticación JWT interna

La aplicación permanece cerrada por defecto con
`AUTHENTICATION_MODE=reject_all`. Para habilitar el contrato interno MarketTec se
deben configurar conjuntamente:

| Variable | Uso |
|---|---|
| `AUTHENTICATION_MODE=jwt` | Activa la validación defensiva en FastAPI |
| `JWT_ISSUER` | Emisor exacto aprobado para el entorno |
| `JWT_AUDIENCE` | Audiencia exacta de `ms-notifications`/gateway |
| `JWT_JWKS_URL` o `JWT_JWKS_JSON` | Endpoint HTTPS o snapshot público revisado; configurar exactamente uno |
| `JWT_DEFAULT_PERMISSIONS` | Capacidades propias concedidas a todo JWT MarketTec válido; por defecto lectura/escritura de recursos propios |
| `JWT_MAX_TTL_SECONDS` | Máximo contractual; no puede superar 240 |

El backend exige firma RS256, encabezados `typ=at+jwt` y `kid`, y claims
`iss`, `aud`, `sub`, `sid`, `iat`, `exp` y `jti`. `sub` es el `userId` interno.
Los JWT actuales de ms-users no incluyen scopes. Por eso, el despliegue concede
explícitamente `notifications:read notifications:write` a cualquier principal
MarketTec válido, siempre limitado por `sub` a sus propios recursos. Si aparecen
`scope`, `scp` o `scopes`, se combinan con esa política. No se confía en headers
de identidad añadidos por el navegador o por APIM.

El paquete de producción de `ms-users` documenta actualmente issuer
`https://markettec-api.azure-api.net/users-prod` y audience `markettec-api`.
La operación JWKS de APIM responde actualmente `404 OPERATION_NOT_RELEASED`. Hasta
liberarla, usar `JWT_JWKS_JSON` con el mismo snapshot público revisado que utiliza
APIM y guardarlo en configuración externa; rotarlo de forma coordinada antes de
retirar un `kid`.

## Notificaciones web en tiempo real (MTEC-26)

`GET /v1/notifications/stream` entrega SSE protegido con el principal y permiso
`notifications:read` de la API de historial. El cliente usa `fetch` streaming
con `Authorization`; no envía tokens en la URL ni usa `EventSource` nativo
mientras la autenticación sea Bearer.

El endpoint admite `Last-Event-ID`, heartbeats, resincronización y límites de
conexiones. La decisión y las pruebas pendientes con Angular/APIM están en
[`docs/MTEC-26_REALTIME_SSE.md`](docs/MTEC-26_REALTIME_SSE.md).

## Ruta de implementación

1. **MTEC-22:** núcleo, validación, deduplicación y pruebas (iniciado aquí).
2. **MTEC-23 adaptado:** persistencia Mongo/Cosmos, índices, concurrencia y
   pruebas de integración.
3. **MTEC-24:** consumidor de Azure Queue, reintentos y poison queue.
4. **MTEC-25:** API autenticada para historial y marcado de lectura.
5. **MTEC-27:** App Service, configuración segura, APIM, CI/CD y evidencias.
6. **MTEC-26:** SSE autenticado después de resolver el mecanismo compatible
   con navegador y APIM.

La preparación vigente de App Service, WebJob, OIDC y verificación operativa de
MTEC-27 está en
[`docs/MTEC-27_AZURE_DEPLOYMENT.md`](docs/MTEC-27_AZURE_DEPLOYMENT.md).
