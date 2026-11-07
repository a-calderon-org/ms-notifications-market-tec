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
