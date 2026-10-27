# Read EventGate in this order

You do not need to understand Celery internals to learn the API. Start with a
simple route, then follow one request through validation and the database.

## Project files

1. **`app/main.py`** creates the FastAPI app, attaches routes, serves CSS/JS,
   and exposes `/health/`. No tables are created by importing this module.
2. **`app/schemas.py`** describes JSON. `Field(ge=1, le=20)` means an integer
   must be between 1 and 20. Invalid input gets an HTTP 422 response automatically.
   Output classes deliberately exclude endpoint secrets and password hashes.
3. **`app/database.py`** provides `get_db()`. FastAPI calls it for each request,
   passes the session into your route, and closes it afterward. `yield` means
   "lend this session to the request, then clean it up."
4. **`app/models.py`** describes storage. `owner_id` connects records to users.
   Database uniqueness rules protect subscriptions and idempotency keys even
   when requests arrive together.
5. **`app/api.py`** contains ordinary `def` functions. Start at `list_endpoints`
   and `create_endpoint`; these show the basic read/write pattern.
6. **`app/security.py`** hashes passwords and checks authentication. API clients
   use expiring signed bearer tokens; browser users use signed session cookies.
   These tokens are signed using ItsDangerous, not JWT. They expire after one
   hour and become invalid when the user's password changes.
7. **`app/web.py`** renders login/dashboard HTML. Browser writes need a CSRF token;
   this prevents another website from using your logged-in browser to make changes.
8. **`app/delivery.py`** sends signed webhooks and records attempts.
   **`app/tasks.py`** lets Celery run that function in a separate process.

## Follow a POST to `/api/events/`

1. FastAPI parses the JSON using `EventCreate`.
2. `Depends(get_current_user)` identifies the user, or responds with HTTP 401.
3. `Depends(get_db)` gives the function a database session.
4. The route checks whether this user already used the idempotency key. Matching
   content returns the original event (HTTP 200); different content returns 409.
5. It creates the event and one pending delivery per matching active subscription.
6. `db.commit()` saves those rows together. `flush()` earlier only obtained an ID;
   it did not permanently save half the request.
7. Celery receives delivery IDs, not secrets or event payloads.
8. The worker sends the payload and saves the response plus attempt history.

If Redis is down, the saved pending rows remain. Celery Beat runs a small task
every five seconds to find due work. That also drives retries and recovers work
after a worker crash. Beat runs inside the single worker service using `--beat`.
For a larger deployment, run one dedicated Beat process before adding worker
replicas. Never run multiple embedded Beat schedulers intentionally.

## Retries, leases, and replay

With a base delay of 5 seconds, failed attempts wait 5, 10, 20, 40... seconds
(capped at one day), plus up to one scheduler interval. `max_attempts` includes
the first send. A final failure becomes `DEAD_LETTERED`.

A database update claims a delivery for 60 seconds. A second worker cannot
claim it during that lease. The worker has a 40-second hard time limit so a
stuck network request is killed before another worker can recover the lease.

Delivery is **at least once**, not exactly once: if a receiver accepts a request
and the worker crashes before saving success, it may be sent again. Receivers
should deduplicate using `X-EventGate-Delivery-ID`. A manual replay creates a new
delivery ID, keeps the old history, and gets its own attempt budget. Replay is
restricted to dead-lettered deliveries so it cannot compete with automatic retries.

## Why ordinary `def` instead of `async def` everywhere?

SQLAlchemy here uses ordinary synchronous database calls. FastAPI runs these
route functions in a thread pool. This is simpler to learn and avoids pretending
that blocking database code is asynchronous. Slow webhook calls run in Celery.

## Exercises

- Read `create_endpoint`, then add one field to its schema and model.
- Generate a migration with `alembic revision --autogenerate -m "describe change"`;
  inspect it before running `alembic upgrade head`.
- Read the ownership test and explain why another user sees HTTP 404.
- Change the test receiver's HTTP status and watch delivery attempts in the dashboard.

References: [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/),
[SQLAlchemy ORM quickstart](https://docs.sqlalchemy.org/en/20/orm/quickstart.html),
[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html).
