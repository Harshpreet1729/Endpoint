# FastAPI migration verification

Verified on 27 October 2026. This records local checks, not a Railway deployment.

| Check | Result |
| --- | --- |
| FastAPI suite | 30 tests passed after cleanup; two importer-only tests removed |
| Real Celery consumer and HTTP receiver | Passed with SQLite and an in-memory broker; failure followed by a successful signed retry |
| Alembic | Repeated upgrade and schema comparison passed; unrelated tables preserved |
| Production configuration | Rejects SQLite, missing secret/Redis variables, wildcard hosts, and private-webhook override |
| Dependency compatibility | `pip check` passed |
| Local and isolated test Compose files | `docker compose config --quiet` passed |
| Browser workflow | Login, endpoint creation, subscription, event creation, and logout passed |
| Browser layout | Desktop and 390-pixel mobile checks passed; no page-level horizontal overflow or captured browser errors |
| Full Docker integration | Not run: Docker Desktop's Linux engine pipe is unavailable |
| Railway / external webhook receiver | Not deployed or tested |

The test suite emits one upstream deprecation warning about Starlette's `httpx`
TestClient adapter. It does not affect the passing tests or application startup.

## Reproduce

```powershell
.\.venv-fastapi\Scripts\python.exe -m pytest -q
.\.venv-fastapi\Scripts\python.exe -m pip check
.\.venv-fastapi\Scripts\python.exe -m alembic check
docker compose config --quiet
```

Once Docker Desktop reports that its engine is running:

```shell
docker compose -p eventgate-fastapi-qa -f tests/compose.yml up --build -d
docker compose -p eventgate-fastapi-qa -f tests/compose.yml run --rm smoke
docker compose -p eventgate-fastapi-qa -f tests/compose.yml down --volumes
```

These commands use an isolated disposable test stack. Its smoke test exercises
PostgreSQL, Redis, a Celery worker, HTTP delivery, retry limits, HMAC, idempotency,
dead-lettering, and replay. The cleanup command deletes only that test stack's
volumes.

## Repository cleanup

The previous framework, its local database and virtual environment, its import
utility, and importer-only tests were removed at the user's request. The active
FastAPI database and environment remain. No push or cloud deployment was performed.

Run the isolated integration test before pushing for Railway's GitHub integration.
Configure both services
with the commands documented in the README.
