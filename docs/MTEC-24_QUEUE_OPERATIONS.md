# MTEC-24: operación del consumidor Azure Queue

## Colas y serialización

- Entrada: `message-sent-v1`.
- Cuarentena: `message-sent-v1-poison`.
- Contenido: un único objeto JSON UTF-8 que cumpla
  `contracts/events/message-sent.v1.schema.json`.
- El productor no debe envolver el JSON en Markdown ni codificarlo en Base64.
- Límite: 64 KiB por mensaje. El consumidor rechaza contenido mayor aunque el
  servicio permita recibirlo por alguna ruta alternativa.
- `eventId` identifica la entrega lógica y `correlationId` permite rastrearla.
  Ninguno de los dos sustituye la autenticación del productor.

## Política de procesamiento

1. El worker recibe un mensaje con visibility timeout configurable (30 segundos
   por defecto).
2. Valida tamaño, JSON, tipo, versión y campos del evento.
3. Persiste la notificación de forma idempotente por
   `(recipientUserId, eventId)`.
4. Solo después de completar o reconocer un duplicado elimina el mensaje.

El procesamiento actual realiza una única escritura corta y debe terminar antes
del visibility timeout. No se renueva el lease porque no hay tareas largas. Si
se agrega I/O adicional que pueda superar ese tiempo, debe implementarse
renovación mediante `update_message` antes de desplegar ese cambio.

## Clasificación de fallos

| Categoría | Ejemplos | Acción |
|---|---|---|
| Permanente | JSON inválido, contrato inválido, más de 64 KiB | Poison inmediato |
| Versión desconocida | `schemaVersion` distinta de `1.0` | Poison inmediato con categoría propia |
| Transitorio | DocumentDB temporalmente no disponible | Reintentar al vencer visibility timeout |
| Infraestructura Queue | Fallo de receive/send/delete | Mantener vivo el worker y reintentar el ciclo |

Los fallos transitorios pasan a poison al alcanzar
`QUEUE_MAX_DEQUEUE_COUNT` (5 por defecto). El envío a poison siempre ocurre
antes de borrar el original. Si ese envío falla, el original no se elimina.

## Logs y privacidad

Los eventos operativos usan pares `clave=valor`, por ejemplo:

```text
event=queue_message_processed event_id=<uuid> correlation_id=<id> created=true
event=queue_message_failed disposition=retry category=transient_processing
event=queue_message_failed disposition=poison category=invalid_json
```

No se registra el payload, la URI de DocumentDB, tokens ni credenciales. Los
logs informativos internos de Azure SDK y PyMongo se reducen a `WARNING`.

## Apagado y reinicio

El proceso atiende `SIGINT` y `SIGTERM`. Al recibir una señal deja de solicitar
mensajes nuevos, cierra Queue, repositorio y credencial. Si el proceso termina
después de persistir pero antes de borrar, Azure reentrega el mensaje y el
índice único evita una segunda notificación.

Inicio local:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\src"
python -m ms_notifications.worker
```

Detención local: `Ctrl+C`.

En Azure debe ejecutarse como proceso independiente con Always On y Managed
Identity. La identidad necesita `Storage Queue Data Contributor`; no se usan
claves de la cuenta de Storage.

## Inspección y replay manual de poison

1. Inspeccionar `message-sent-v1-poison` sin publicar el contenido en logs,
   capturas o Jira si contiene datos privados.
2. Identificar y corregir primero la causa en el productor o el contrato.
3. Para un mensaje corregible, copiar únicamente el JSON válido a
   `message-sent-v1`, con Base64 desactivado.
4. Verificar el log `queue_message_processed` y la notificación en DocumentDB.
5. Solo entonces eliminar el mensaje original de poison.

El replay conserva el mismo `eventId`. Por idempotencia, repetirlo no debe crear
otra notificación. No se habilita replay masivo automático: requiere revisión
manual para evitar ciclos de mensajes inválidos.

## Evidencia de aceptación

- Suite local: recepción, duplicado, reinicio, correlación, errores permanentes,
  versión desconocida, fallos transitorios, máximo de intentos, poison y no
  pérdida si falla el envío a poison.
- Prueba manual: mensaje válido consumido desde Azure Queue y documento creado
  en Azure DocumentDB.
- Prueba manual: mensaje Base64/no JSON reintentado por la versión inicial y
  aislado en `message-sent-v1-poison` sin crear documento.
