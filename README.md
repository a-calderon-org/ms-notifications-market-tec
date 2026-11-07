# ms-notifications-market-tec

Núcleo del microservicio de notificaciones de MarketTEC para MTEC-22.

## Alcance

- FastAPI y Python 3.12.
- Arquitectura hexagonal.
- Validación del evento `message.sent.v1`.
- Persistencia en memoria.
- Idempotencia por `eventId`.
- Health checks y pruebas unitarias.

## Inicio rápido

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m uvicorn ms_notifications.api.main:app --app-dir src --reload
```

Endpoints:

- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`
- `http://localhost:8000/docs`

Pruebas:

```powershell
python -m pytest
```

El archivo `.env` y cualquier secreto real están excluidos de Git.

## Persistencia Mongo/DocumentDB

Para usar MongoDB local o Azure DocumentDB compatible con MongoDB:

```dotenv
NOTIFICATIONS_REPOSITORY=mongo
MONGODB_URI=<cadena-secreta-solo-en-.env>
MONGODB_DATABASE=market_tec_notifications
MONGODB_COLLECTION=notifications
```

El adaptador crea un índice único por `(recipientUserId, eventId)` para
idempotencia. `compose.yaml` permite iniciar MongoDB local para desarrollo.

## Consumidor Azure Queue

El worker independiente consume `message-sent-v1`, reintenta fallos transitorios
y mueve mensajes permanentes a `message-sent-v1-poison`.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m ms_notifications.worker
```

La política de serialización, apagado y replay manual está documentada en
[`docs/MTEC-24_QUEUE_OPERATIONS.md`](docs/MTEC-24_QUEUE_OPERATIONS.md).
