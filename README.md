# Service Booking API

Foundational backend for a service booking platform using FastAPI, async
SQLAlchemy 2.0, PostgreSQL, and Redis.

## Run locally

1. Optionally copy `.env.example` to `.env` to customize the development
   defaults.
2. Start the stack:

   ```bash
   docker compose up --build
   ```

3. Call the protected health endpoint with a UUID and an allowed role:

   ```bash
   curl http://localhost:8000/health \
     -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
     -H "X-User-Role: admin"
   ```

The expected response is:

```json
{"status":"ok","database":"ok","redis":"ok"}
```

This initial scaffold creates tables on startup for convenience. Replace
`Base.metadata.create_all` with Alembic migrations before production rollout.
