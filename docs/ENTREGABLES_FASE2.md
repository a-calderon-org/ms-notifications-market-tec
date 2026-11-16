# Entregables Fase II: ms-notifications

Mapa de los entregables **b**, **d** y **e** a sus archivos y a la evidencia que hay que
capturar. Sus requisitos corresponden a R08, R11, R25–R28 y R31 de
`market_tec/context/phase2/REQUIREMENTS_TRACEABILITY.md`.

**Regla para toda la evidencia:** no mostrar connection strings, keys, tokens, valores
de named values ni la URI de Mongo. Recortar o censurar antes de entregar.

---

## b. API Management con documentación de seguridad (Postman + Swagger)

| Pieza | Archivo / lugar |
|---|---|
| Configuración de APIM (policy como código) | [`infra/apim/notifications-api-policy.xml`](../infra/apim/notifications-api-policy.xml), generada por [`build_notifications_policy.py`](../infra/apim/build_notifications_policy.py) |
| Documentación de seguridad (controles, limitaciones y pasos para aplicar) | [`infra/apim/README.md`](../infra/apim/README.md) |
| Swagger / OpenAPI con el esquema `bearerAuth` y el modelo de seguridad | [`contracts/openapi/notifications.json`](../contracts/openapi/notifications.json); también en APIM > APIs > Notifications > *OpenAPI* y en `http://localhost:8000/docs` |
| Pruebas de seguridad en Postman | Carpeta **03 Security** de la colección (401, 400, 404, 403) |

**Capturas a tomar** (después de aplicar los pasos de `infra/apim/README.md`):
1. APIM > APIs > *MarketTEC Notifications API*: lista de las 5 operaciones.
2. APIM > API > *All operations* > Inbound processing (editor de código) con `validate-jwt` visible.
3. APIM > Named values: `notifications-backend-key` marcado como **Secret** (sin el valor).
4. App Service > Environment variables: `APIM_GATEWAY_KEY` con la referencia a Key Vault en verde, y `AUTHENTICATION_MODE=jwt`.
5. Postman Runner (o newman) con la carpeta 03 Security en verde.
6. Respuesta `403 DIRECT_ACCESS_FORBIDDEN` al llamar directo al hostname de App Service.

## d. Tres servicios de almacenamiento distintos en Azure

El requisito se cumple a nivel de **proyecto**: cada microservicio usa un servicio distinto.

| # | Tipo | Servicio Azure | Microservicio | Recurso | Dato |
|---|---|---|---|---|---|
| 1 | Relacional | **Azure SQL Database** | ms-users | `sql-markettec-dev` / `sqldb-ms-users-dev` | Usuarios, identidades, sesiones |
| 2 | NoSQL documental | **Azure Cosmos DB for NoSQL** | ms-catalog | contenedores `publicaciones`, `chats`, `mensajes` | Catálogo y chat |
| 3 | Objetos / mensajería | **Azure Storage**: Blob + Queue | ms-catalog / ms-notifications | Blob `publication-images`; Queue `stmtecnotifdevcc/message-sent-v1` (+ `-poison`) | Imágenes y eventos `message.sent.v1` |
| + | NoSQL compatible con MongoDB | **Azure DocumentDB** (Mongo vCore) | ms-notifications | `cosmos-mtec-notif`, DB `market_tec_notifications`, colección `notifications` | Notificaciones persistidas |

> La matriz original preveía Azure Table Storage para notificaciones (R16/R19).
> La implementación usa DocumentDB (ver README). Si el docente exige que *cada*
> microservicio tenga un tipo distinto, esta fila también cumple, porque no repite
> los servicios de los otros dos.

**Evidencia de ms-notifications** (responsable: ms-notifications). Comandos verificados
el 15-11-2026, solo lectura:

```bash
# DocumentDB: estado del cluster
az resource show -g rg-markettec-notifications-dev-cc -n cosmos-mtec-notif \
  --resource-type Microsoft.DocumentDB/mongoClusters \
  --query "{name:name,status:properties.clusterStatus,version:properties.serverVersion,tier:properties.compute.tier}"

# Queue Storage: colas por el plano de control (el firewall bloquea el plano de datos desde fuera de la VNet)
SUB=$(az account show --query id -o tsv)
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/rg-markettec-notifications-dev-cc/providers/Microsoft.Storage/storageAccounts/stmtecnotifdevcc/queueServices/default/queues?api-version=2023-05-01" --query "value[].name"
```

Capturas:
1. Portal > `cosmos-mtec-notif` > Overview (tipo, región, estado *Ready*).
2. Datos reales: un documento de la colección `notifications` (Data Explorer, mongosh o Compass desde una IP permitida), con `recipientUserId` censurado.
3. Portal > `stmtecnotifdevcc` > Queues: `message-sent-v1` y `message-sent-v1-poison`.
4. Mensaje procesado: log de Application Insights con el mismo `correlation_id` en el evento y en la notificación (MTEC-27 §4, pasos 8-9).
5. Networking de la Storage Account: *Selected networks* (acceso público deshabilitado salvo la VNet).

**Evidencia de los otros servicios** (pedir a los responsables): Azure SQL (Overview y
Query editor con la tabla de usuarios censurada), Cosmos DB for NoSQL (Data Explorer
con una publicación) y Blob (contenedor `publication-images` con una imagen).

## e. Colección de Postman exportada (JSON)

| Archivo | Contenido |
|---|---|
| [`docs/postman/ms-notifications.postman_collection.json`](postman/ms-notifications.postman_collection.json) | 20 requests en 4 carpetas, con tests en cada una (v2.1) |
| [`docs/postman/environments/markettec-apim.postman_environment.json`](postman/environments/markettec-apim.postman_environment.json) | `baseUrl` = APIM, `directBaseUrl` = App Service |
| [`docs/postman/environments/local.postman_environment.json`](postman/environments/local.postman_environment.json) | Desarrollo local |

| Carpeta | Endpoints |
|---|---|
| 01 Health | `GET /health/live`, `GET /health/ready` |
| 02 Notifications | `GET /v1/notifications` (con paginación), `PATCH /v1/notifications/{id}/read` (incluida la prueba de idempotencia) |
| 03 Security | 401 (sin token, no Bearer, firma falsa, `alg=none`, expirado, header suplantado), 400 (correlation id, pageSize, cursor, UUID), 404 (notificación ajena), 403 (acceso directo y clave falsificada) |
| 04 Realtime SSE | `GET /v1/notifications/stream` (manual) |

**Token:** iniciar sesión en la SPA, abrir DevTools > Network, copiar el valor del header
`Authorization` (sin `Bearer `) de un request a `markettec-api.azure-api.net` y pegarlo
en `bearerToken` del environment. Dura 240 s, así que hay que ejecutar enseguida. Para
`expiredToken`, guardar un token y usarlo pasados 5 minutos.

**Ejecutar y exportar resultados** (R28):

```bash
npx -y newman@6.2.1 run docs/postman/ms-notifications.postman_collection.json \
  -e docs/postman/environments/markettec-apim.postman_environment.json \
  --env-var "bearerToken=<token>" \
  --folder "01 Health (público)" --folder "02 Notifications (JWT)" --folder "03 Security" \
  --reporters cli,json --reporter-json-export newman-results.json
```

No subir `newman-results.json` ni un environment con un token cargado.

Verificado el 15-11-2026 en local, con el autenticador JWT real y una clave RSA de prueba:
16 requests, 65 aserciones, 0 fallas. Contra APIM, antes de aplicar la policy, ya pasan
los 401; health (404) y los 403 dependen de los pasos de `infra/apim/README.md`.

> Si el entregable **e** se evalúa a nivel de proyecto, esta colección cubre
> ms-notifications. Hay que combinarla con las de ms-users y ms-catalog en una sola
> exportación, con una carpeta por servicio.
