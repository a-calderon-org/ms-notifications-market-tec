# MTEC-27: despliegue manual y reproducible en Azure

Esta guía prepara el API FastAPI y el consumidor de Queue en un App Service
Linux. No ejecuta cambios Azure por sí sola. Todos los nombres y valores deben
revisarse antes de crearlos en la suscripción Azure for Students.

## Estado y límites actuales

- Ya existen `cosmos-mtec-notif` y `stmtecnotifdevcc` en Canada Central.
- Todavía no existen App Service Plan, Web App, Key Vault ni Application
  Insights en `rg-markettec-notifications-dev-cc`.
- La API usa `startup.sh`; el worker se despliega como WebJob continuo bajo
  `App_Data/jobs/continuous/notifications-worker/run.py`.
- Un WebJob continuo confiable requiere **Always On**, disponible desde Basic.
  Un plan B1 genera cobro mientras exista, incluso sin tráfico.
- No configurar APIM/JWT hasta que el equipo cierre MTEC-12. No copiar una
  subscription key o un token al repositorio ni al frontend.
- El nivel APIM Consumption no admite SSE de larga duración. MTEC-26 debe
  conservarse separado hasta elegir un nivel compatible o transporte distinto.

## 1. Crear recursos desde el portal

En el grupo `rg-markettec-notifications-dev-cc`, región Canada Central:

1. Crear un **App Service Plan Linux**, SKU Basic B1 como mínimo para Always On.
2. Crear una **Web App** con nombre global único, runtime Python 3.12 y el plan
   anterior.
3. En Identity, habilitar la identidad administrada asignada por el sistema.
4. Crear Application Insights y asociarlo a la Web App.
5. Crear Key Vault con RBAC habilitado. Guardar la URI Mongo completa como
   secreto `mongodb-uri`; no pegarla en GitHub ni en capturas.
6. Asignar a la identidad de la Web App:
   - `Storage Queue Data Contributor` sobre `stmtecnotifdevcc`.
   - `Key Vault Secrets User` sobre el Key Vault.
7. En la Web App, copiar **Outbound IP addresses**. Agregar solamente esas IP
   al firewall de DocumentDB y, si Storage restringe redes, al Storage Account.
   La identidad administrada autoriza, pero no atraviesa un firewall cerrado.
8. En Configuration > General settings:
   - Startup Command: `bash startup.sh`.
   - Always On: `On`.
   - HTTPS Only: `On`.

Antes de crear B1, revisar **Cost analysis** y el crédito estudiantil. Eliminar
el plan al terminar el laboratorio si no se necesita conservar el servicio.

## 2. Configurar variables de la Web App

Agregar en Environment variables, sin espacios adicionales:

| Nombre | Valor |
|---|---|
| `APP_ENV` | `development` |
| `LOG_LEVEL` | `INFO` |
| `NOTIFICATIONS_REPOSITORY` | `mongo` |
| `MONGODB_URI` | referencia Key Vault a `mongodb-uri` |
| `MONGODB_DATABASE` | `market_tec_notifications` |
| `MONGODB_COLLECTION` | `notifications` |
| `AZURE_STORAGE_QUEUE_ENDPOINT` | `https://stmtecnotifdevcc.queue.core.windows.net` |
| `AZURE_QUEUE_NAME` | `message-sent-v1` |
| `AZURE_POISON_QUEUE_NAME` | `message-sent-v1-poison` |
| `QUEUE_VISIBILITY_TIMEOUT_SECONDS` | `30` |
| `QUEUE_MAX_DEQUEUE_COUNT` | `5` |
| `QUEUE_POLL_INTERVAL_SECONDS` | `5` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | valor creado por la integración del portal |
| `ApplicationInsightsAgent_EXTENSION_VERSION` | `~3` |
| `OTEL_SERVICE_NAME` | `ms-notifications` |

La referencia Key Vault tiene la forma que genera el selector del portal. No
copiar el valor real del secreto a la configuración visible o al workflow.

## 3. Preparar GitHub OIDC

La opción recomendada es abrir la Web App > Deployment Center, seleccionar el
repositorio y **User-assigned identity / OpenID Connect**. Configurar el ambiente
GitHub `development` con aprobación manual y estos valores:

Secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Variables:

- `AZURE_WEBAPP_NAME`: nombre exacto de la Web App.
- `AZURE_WEBAPP_URL`: URL HTTPS sin `/` final.

No usar publish profile. El workflow `Deploy development` solo aparece como
`workflow_dispatch` y exige marcar la confirmación `deploy`.

## 4. Desplegar y verificar

1. Fusionar el PR de MTEC-27 después de revisión.
2. Abrir Actions > Deploy development > Run workflow.
3. Seleccionar `main`, activar `deploy` y aprobar el ambiente.
4. Confirmar que `Validate`, `Deploy` y `Verify liveness` finalizan en verde.
5. Abrir `https://<app>/health/live`: debe devolver `{"status":"ok"}`.
6. Abrir `/health/ready`: debe indicar repositorio `mongo` y estado `ok`.
7. En Web App > WebJobs confirmar `notifications-worker` en ejecución.
8. Enviar un evento de prueba sin datos personales a `message-sent-v1`.
9. Confirmar que desaparece de la cola, aparece una sola notificación en
   DocumentDB y los logs muestran el mismo `correlation_id`.
10. Repetir el mismo `eventId`: no debe crear otro documento.
11. Enviar un evento inválido y confirmar su movimiento a
    `message-sent-v1-poison` sin secretos en logs.

## 5. APIM y acceso directo

Esta etapa queda pendiente de MTEC-12 y no debe improvisarse desde este ticket.
Cuando exista una decisión aprobada:

1. Importar el OpenAPI del commit revisado.
2. Aplicar validación real de issuer, audience, firma, expiración y permisos.
3. Eliminar headers de identidad proporcionados por el cliente.
4. Probar token válido, ausente, expirado, firma/audience incorrectos y acceso
   directo al hostname de App Service.
5. Restringir el origen solo después de verificar un mecanismo APIM→backend
   compatible con el nivel realmente contratado.

No marcar MTEC-27 Done solamente porque la URL de App Service responde.

## 6. Evidencia y reversión

Guardar en el PR/Jira, sin secretos:

- URL APIM y Web App censurada cuando corresponda, estado de health y fecha.
- ID del run de CI/deploy, commit y versión Python.
- Evidencia de Queue, poison, deduplicación y Application Insights.
- Resultado de pruebas 401/403 y acceso directo cuando MTEC-12 lo permita.

Para revertir, volver a desplegar el último commit estable desde Actions. Si el
servicio queda inestable, detener la Web App antes de alterar datos o colas. No
eliminar DocumentDB, Storage Account o el grupo de recursos como parte de un
rollback de código.
