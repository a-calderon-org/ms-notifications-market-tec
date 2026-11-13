# MTEC-26: entrega web en tiempo real mediante SSE

## Decisión para el incremento local

El backend expone `GET /v1/notifications/stream` como `text/event-stream`. El
cliente web debe abrirlo mediante `fetch` con streaming para enviar el token en
`Authorization: Bearer ...`. No se admiten tokens en query strings y no se usa
`EventSource` nativo, porque este no permite configurar el encabezado
`Authorization`.

Esta decisión es provisional hasta completar la prueba real con Angular, APIM y
App Service. El autenticador por defecto continúa rechazando todas las
credenciales hasta que App Service active `AUTHENTICATION_MODE=jwt` (MTEC-27).

## Comportamiento del servidor

- El principal autenticado determina el `recipientUserId`; el cliente nunca lo
  envía como parámetro.
- El stream consulta la persistencia de forma independiente al worker. Un
  navegador desconectado no impide guardar una notificación.
- Cada notificación incluye `id`, tipo `notification` y un JSON sin
  `recipientUserId`.
- El cliente conserva el último `id` procesado y lo envía como
  `Last-Event-ID` al reconectar.
- Si el identificador ya no está en la ventana de consulta, el servidor emite
  `event: resync`. El cliente recupera `/v1/notifications` y reabre el stream.
- Se envían comentarios `keep-alive`, se detectan desconexiones y se liberan
  contadores en un bloque `finally`.
- Los límites predeterminados son 100 conexiones por instancia y 3 por usuario.
  Un exceso responde `429` con `Retry-After: 5`.
- Cada conexión dura como máximo 300 segundos. El cliente reconecta y vuelve a
  presentar sus credenciales; un token expirado debe producir `401`.

## Cliente web de referencia

La obtención y renovación real del token depende del contrato de identidad.

```javascript
async function openNotificationStream(accessToken, lastEventId, signal) {
  const headers = {
    Accept: "text/event-stream",
    Authorization: `Bearer ${accessToken}`,
  };
  if (lastEventId) headers["Last-Event-ID"] = lastEventId;

  const response = await fetch("/v1/notifications/stream", {
    headers,
    signal,
    credentials: "omit",
  });

  if (response.status === 401) throw new Error("session-expired");
  if (response.status === 429) throw new Error("connection-limit");
  if (!response.ok || !response.body) throw new Error("stream-unavailable");

  return response.body.pipeThrough(new TextDecoderStream()).getReader();
}
```

Angular debe usar un parser SSE probado o cubierto con fragmentación de red,
múltiples líneas `data`, UTF-8 y cancelación. Un simple `split("\n\n")` no es
suficiente para producción.

## Variables

```dotenv
SSE_POLL_INTERVAL_SECONDS=2
SSE_HEARTBEAT_INTERVAL_SECONDS=15
SSE_BATCH_SIZE=100
SSE_MAX_CONNECTIONS=100
SSE_MAX_CONNECTIONS_PER_USER=3
SSE_MAX_CONNECTION_DURATION_SECONDS=300
```

## Verificación pendiente antes de Done

1. Validar JWT real de ms-users, expiración y renovación (contrato aprobado en
   MTEC-12/MTEC-36).
2. Comprobar que APIM y cualquier proxy no almacenen ni acumulen el stream.
3. Ejecutar en navegador reconexión, `401`, `429`, cancelación e historial.
4. Medir conexiones, duración, desconexiones, latencia y errores en Application
   Insights sin registrar tokens.
5. Confirmar capacidad y timeouts de App Service/APIM antes de fijar SSE como
   mecanismo definitivo.
