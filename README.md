# EventGate — FastAPI

Send signed webhooks, subscribe endpoints to event types, retry failures, and
replay dead-lettered deliveries. Python 3.13, FastAPI, SQLAlchemy, Celery, Redis,
and either SQLite locally or PostgreSQL in production.

New to FastAPI? Start with [the learning guide](docs/LEARNING_FASTAPI.md).
It explains the files and follows a request through this project.

## Run locally with Docker (recommended, especially on Windows)

Start Docker Desktop, then:

```shell
docker compose up --build -d
docker compose exec web python -m app.cli create-user YOUR_NAME
```

The second command prompts privately for a password. Open
[the dashboard](http://localhost:8000/api/dashboard/) and sign in. Add an
endpoint, subscribe it to `order.created`, and create an event. Use a unique
[webhook.site](https://webhook.site/) URL to receive a test delivery.

The web service applies migrations before startup. Both web and worker share
`fastapi.sqlite3` through the bind mount. Redis has a persistent development
volume. Only the web service and localhost Redis port are published.

```shell
docker compose logs -f celery
docker compose down
```

`down` stops containers; don't add `--volumes` unless you intend to discard Redis data.

## Run Python directly

Use `.venv-fastapi` as the isolated Python environment for this project.
In PowerShell:

```powershell
python -m venv .venv-fastapi
.\.venv-fastapi\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.cli create-user YOUR_NAME
python -m uvicorn app.main:app --reload
```

Redis must be running for task delivery (`docker compose up -d redis` is enough).
Run the worker on Linux, WSL, or Docker; Celery does not officially support
native Windows workers:

```shell
celery -A app.celery_app:celery_app worker --beat --loglevel=info --concurrency=2 --schedule=/tmp/eventgate-beat
```

The web UI and API can run without a worker, but deliveries stay pending.
`.env.example` documents the variables; native Python reads environment variables,
not `.env` automatically. In PowerShell use `$env:NAME='value'`.

## API workflow

Open [Swagger UI](http://localhost:8000/docs), click **Authorize**, and enter the
user/password created above. Swagger obtains a one-hour bearer token from
`POST /api/auth/token`. Browser login still lives at `/api-auth/login/`.

1. `POST /api/endpoints/`:

   ```json
   {"name":"Test receiver","url":"https://webhook.site/YOUR-ID","secret":"your-test-signing-secret","max_attempts":5,"retry_base_delay":5}
   ```

2. `POST /api/subscriptions/`, using the returned endpoint ID:

   ```json
   {"endpoint":1,"event_type":"order.created"}
   ```

3. `POST /api/events/`:

   ```json
   {"event_type":"order.created","payload":{"order_id":1},"idempotency_key":"order-1-created"}
   ```

4. `GET /api/deliveries/` and `GET /api/deliveries/1/attempts/` show results.
5. `POST /api/deliveries/1/replay/` replays a dead-lettered delivery asynchronously.

Only matching active subscriptions receive an event. Events without a matching
subscription are stored without deliveries. Listing endpoints/events/subscriptions/
deliveries supports `offset` and `limit` (default/max 100).

The `Idempotency-Key` header can replace the JSON key. Repeating the same key and
content returns the original event (200); conflicting content returns 409. Keys
are scoped to a user and enforced by a database constraint.

`PUT /api/endpoints/{id}/` replaces an endpoint's settings, including its secret.
`DELETE /api/endpoints/{id}/` deactivates it, preserving delivery history.
`DELETE /api/subscriptions/{id}/` unsubscribes it. Every API query is owner-scoped.

Webhook bodies use compact JSON with sorted keys. `X-EventGate-Signature` is the
hexadecimal HMAC-SHA256 of the exact body using the endpoint secret. Compare
signatures using a constant-time comparison in the receiver. Responses are capped
at 64 KiB; redirects are treated as failures. Private/reserved IP destinations are
blocked, including hostnames that resolve to them. For a local test receiver only,
set `DEBUG=True` and `ALLOW_PRIVATE_WEBHOOKS=True` on the worker.

## Railway deployment

Use separate `web`, `worker`, `Postgres`, and `Redis` services in the same project
and environment. Both app services build the root Dockerfile from GitHub. Only
`web` needs a public domain. Use the private database variables below. Database
backups, volume persistence, monitoring, and usage limits remain operator settings.

Web variables:

```dotenv
SECRET_KEY=<random-secret-at-least-50-characters>
DEBUG=False
ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app
CSRF_TRUSTED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
```

Worker: the same `SECRET_KEY`, `DEBUG`, `DATABASE_URL`, and both `CELERY_*` variables;
set `ALLOWED_HOSTS=healthcheck.railway.app` if running production checks outside
Railway (the platform hostname is automatically included inside Railway).
Production startup fails with SQLite, a weak/missing secret, missing Redis URLs,
or private-webhook access enabled. Generate secrets privately; never commit them.

**Set these commands in Railway's service settings.** Dashboard command
overrides are not changed automatically by a new Dockerfile.

Web pre-deploy (only here, one deployment at a time):

```shell
alembic upgrade head
```

Web start (shell wrapper expands Railway's `PORT`):

```shell
/bin/sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips "*"'
```

Trusting forwarded headers here assumes all incoming public traffic comes through
Railway's trusted proxy. Do not copy that wildcard to an untrusted direct server.
Railway handles public HTTPS; the application keeps `/health/` available over HTTP
for internal checks. Set web healthcheck to `/health/`; it checks database/schema
access. Static CSS/JS are served by FastAPI; no `collectstatic` is required.

Worker start:

```shell
celery -A app.celery_app:celery_app worker --beat --loglevel=info --concurrency=2 --schedule=/tmp/eventgate-beat
```

Keep **one worker replica** with embedded Beat. Beat recovers pending work and
schedules retries every five seconds; it must remain running. Before scaling,
split out exactly one Beat scheduler and remove `--beat` from the worker command.
Do not enable sleeping for the worker. No worker HTTP healthcheck or migration
command is needed. Web and worker must deploy the same revision.

Create a user with `python -m app.cli create-user YOUR_NAME` in the web
container. `reset-password` is also available. Manage EventGate through the
dashboard, `/docs`, bearer tokens, and CLI. There is no public signup,
automatic admin panel, or password-reset email flow.

## Verification

```shell
python -m pytest -q
alembic check
```

The tests cover the original success/failure/retry/dead-letter scenarios plus
authentication, CSRF, ownership, idempotency, subscriptions, replay, HMAC, unsafe
destinations, queue outages, scheduler recovery, schema migration, and production configuration.

With Docker Desktop running, the following isolated stack tests actual PostgreSQL,
Redis, Celery, and HTTP delivery (no external webhook service required):

```shell
docker compose -p eventgate-fastapi-qa -f tests/compose.yml up --build -d
docker compose -p eventgate-fastapi-qa -f tests/compose.yml run --rm smoke
docker compose -p eventgate-fastapi-qa -f tests/compose.yml down --volumes
```

The final command deletes only this disposable test stack's volumes. The test
receiver fails once to exercise retries and always fails on another route to
exercise dead-lettering/replay. `web` is exposed locally on port 18081 for inspection.

Before publishing, verify the Railway domain, login, dashboard CSS, event creation,
worker task completion, receiver HMAC header, and saved attempt records. App tests
do not establish a live Railway deployment. For an internet-facing multi-user
service, also configure login rate limiting at the edge and operational alerting.
