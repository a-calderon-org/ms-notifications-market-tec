# MTEC-25: API de historial y lectura

## Estado del alcance

| Área | Estado | Evidencia |
|---|---|---|
| Casos de uso hexagonales | Implementado | `application/notification_history.py` |
| Persistencia en memoria | Implementado | pruebas de paginación, lectura y aislamiento |
| Adaptador Mongo/DocumentDB | Implementado | consulta por destinatario y actualización atómica probadas con mocks |
| Endpoints FastAPI | Implementado | pruebas HTTP de 200/400/401/403/404 |
| OpenAPI | Implementado como borrador local | `contracts/openapi/notifications.json` |
| Autenticación en pruebas | Simulada | `FakeAuthenticator` existe únicamente en tests |
| JWT/APIM productivo | Pendiente externo | MTEC-12 y MTEC-15 |

La aplicación usa `RejectAllAuthenticator` por defecto. Por lo tanto, ningún
token falso o header de identidad habilita los endpoints al ejecutar el servicio
normalmente. Un autenticador productivo solo debe añadirse después de aprobar y
probar el contrato transversal de identidad.

## Endpoints

### `GET /v1/notifications`

- Requiere permiso `notifications:read`.
- Obtiene el destinatario únicamente desde `AuthenticatedPrincipal.user_id`.
- `pageSize`: 1 a 100; valor predeterminado 20.
- `cursor`: opaco, URL-safe y estable por `(createdAt, eventId)` descendente.
- No acepta `recipientUserId` desde el cliente.
- Devuelve `occurredAt` y `createdAt` como Epoch seconds.

### `PATCH /v1/notifications/{notificationId}/read`

- Requiere permiso `notifications:write`.
- La operación es idempotente.
- El filtro de persistencia incluye simultáneamente destinatario e identificador.
- Un identificador inexistente o perteneciente a otro usuario devuelve el mismo
  `404`, evitando revelar propiedad ajena.

## Correlación y errores

Cada respuesta devuelve `X-Correlation-ID`. El cliente puede enviar uno con 1 a
128 caracteres seguros; si lo omite, el servicio genera un UUID. Formato:

```json
{
  "error": {
    "code": "UNAUTHENTICATED",
    "message": "A valid authenticated session is required",
    "correlationId": "..."
  }
}
```

Los errores documentados son 400, 401, 403 y 404. No se incluyen detalles del
repositorio ni datos de otros usuarios.

## Postman y pruebas

Importar `docs/postman/MTEC-25.postman_collection.json`. La colección no contiene
tokens. `bearerToken` debe permanecer vacío hasta disponer de un token legítimo
del flujo aprobado; las pruebas automatizadas cubren actualmente todos los
endpoints con un autenticador falso inyectado solo durante tests.

Ejecutar:

```powershell
python -m pytest
python -m ruff check src tests
```

## Puerta de despliegue

No exponer estos endpoints en un ambiente compartido o productivo hasta que:

1. MTEC-12/MTEC-15 definan issuer, audience, firma, expiración y permisos.
2. APIM elimine headers de identidad entrantes no confiables.
3. El backend valide o reciba de forma demostrablemente confiable el principal.
4. Se prueben tokens inválidos, expirados, audiencia/firma incorrecta y bypass.
