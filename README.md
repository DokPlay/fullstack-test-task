# Secure File Exchange Dashboard

[Русская версия](./README.ru.md)

Secure File Exchange Dashboard is a full-stack file exchange MVP. It lets users upload documents, stores file metadata in PostgreSQL, processes files asynchronously with Celery, detects suspicious content signals, sends alerts, and updates the dashboard in real time through Server-Sent Events.

The project contains a FastAPI backend, a Next.js frontend, PostgreSQL, Redis, Celery worker, and Celery Beat watchdog, all wired through Docker Compose for reproducible local review.

## Features

- File upload through the web UI and REST API.
- Streaming file writes with `aiofiles`, so uploads are not loaded fully into memory.
- Configurable maximum upload-size guard that returns `413` before oversized uploads can fill local storage.
- PostgreSQL-backed file metadata, processing state, scan result, and alerts.
- Celery background processing with Redis broker/result backend.
- Atomic processing claim to prevent duplicate Celery deliveries from processing the same file twice.
- Watchdog recovery for stale `processing` and stale `uploaded` files.
- Suspicious file detection by extension, oversized files, and PDF MIME mismatch.
- Metadata extraction for text files and PDFs with chunked file reads.
- Server-Sent Events dashboard stream with initial snapshot and patch events.
- Polling retained only as a fallback when realtime updates are unavailable.
- Cascading alert cleanup when a file is deleted.
- Layered backend architecture and feature-sliced frontend structure.

## Tech Stack

Backend:

- Python 3.14
- FastAPI
- SQLAlchemy async ORM
- Alembic
- PostgreSQL
- Redis
- Celery and Celery Beat
- aiofiles

Frontend:

- Next.js 16
- React 18
- TypeScript
- React-Bootstrap
- Bootstrap 5

Infrastructure:

- Docker Compose
- PostgreSQL 16
- Redis 7

## Architecture

### Backend

The backend is split into explicit layers:

- `backend/src/api` contains FastAPI routes and dependency providers.
- `backend/src/core` contains settings, database factory, DI container, and file storage.
- `backend/src/repositories` contains database access logic.
- `backend/src/services` contains business logic, file processing, event publishing, and queue abstractions.
- `backend/src/tasks.py` is the Celery worker entrypoint.

Key backend decisions:

- `ApplicationContainer` is the composition root for settings, storage, repositories, services, event bus, and database lifecycle.
- FastAPI dependencies resolve services from the container instead of constructing services inside route handlers.
- The web app uses a queue adapter and does not import the Celery worker entrypoint.
- Redis publisher and SQLAlchemy engine are closed through FastAPI lifespan.
- Processing starts with a conditional database update, making duplicate worker deliveries idempotent.
- Celery Beat periodically requeues stale files or marks them as failed after the configured retry limit.
- Celery worker and beat drop root privileges in Docker with `--uid nobody --gid nogroup`.

### Frontend

The frontend is organized by feature-sliced layers:

- `frontend/src/app` contains Next.js entrypoints.
- `frontend/src/widgets` contains page-level dashboard blocks.
- `frontend/src/features` contains upload and dashboard monitoring flows.
- `frontend/src/entities` contains domain types, status helpers, and entity UI.
- `frontend/src/shared` contains reusable API, formatting, and UI utilities.

The dashboard opens an SSE connection to `/events`, applies an initial snapshot, and then applies patch events without refetching the whole dashboard after every realtime event. Full refresh remains available as a manual and fallback path.

## Launch

Prerequisites:

- Docker Desktop with Compose support.

Use the standard Docker launch flow.

Start the stack:

```bash
docker compose -f docker-compose.dev.yml up
```

Apply database migrations in a second terminal after the backend container is running:

```bash
docker exec -it backend alembic upgrade head
```

Open frontend: [http://localhost:3000/test](http://localhost:3000/test)

Open backend: [http://localhost:8000/docs](http://localhost:8000/docs)

The `docker compose ... up` command runs in the foreground and streams logs, so keep that terminal open while using the application.

## Additional Options

Backend health checks:

- Liveness: [http://localhost:8000/health/live](http://localhost:8000/health/live)
- Readiness: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- Legacy alias: [http://localhost:8000/health](http://localhost:8000/health)
- Prometheus metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)

Monitoring stack with Prometheus and Grafana:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.monitoring.yml --profile monitoring up -d
docker exec -it backend alembic upgrade head
```

Monitoring URLs:

- Prometheus: [http://localhost:9090](http://localhost:9090)
- Grafana: [http://localhost:3001](http://localhost:3001)
- Grafana login: `admin`
- Grafana password: `admin`
- Backend metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- Worker metrics: [http://localhost:9101/metrics](http://localhost:9101/metrics)
- Beat metrics: [http://localhost:9102/metrics](http://localhost:9102/metrics)

Grafana is provisioned with the default Prometheus datasource automatically, so after login you can open Explore and run queries such as `up`, `http_requests_total`, `file_upload_total`, `file_scan_total`, or `celery_worker_tasks_completed_total`.

Run in detached mode if preferred:

```bash
docker compose -f docker-compose.dev.yml up -d
docker exec -it backend alembic upgrade head
```

If your terminal or CI environment does not support interactive TTY, run migrations without `-it`:

```bash
docker exec backend alembic upgrade head
```

Force image rebuild after code or dependency changes:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Stop the stack:

```bash
docker compose -f docker-compose.dev.yml down
```

Stop the stack and remove the PostgreSQL volume:

```bash
docker compose -f docker-compose.dev.yml down -v
```

## Migration Management

For a fresh local launch, the only required migration command is:

```bash
docker exec -it backend alembic upgrade head
```

Rollback commands are maintenance tools for a failed release or controlled production rollback. They are not part of the normal local startup flow.

Check the current database revision:

```bash
docker exec -it backend alembic current
```

Show migration history:

```bash
docker exec -it backend alembic history --verbose
```

Rollback one migration:

```bash
docker exec -it backend alembic downgrade -1
```

Rollback to a specific revision:

```bash
docker exec -it backend alembic downgrade <revision_id>
```

Return to the latest schema:

```bash
docker exec -it backend alembic upgrade head
```

If your terminal or CI environment does not support interactive TTY, run the same commands without `-it`. Before any downgrade, create a backup of the PostgreSQL database or volume and `backend/storage/files`; schema rollback can remove columns or constraints and may not restore data that was already transformed or dropped.

## Connect To A Website Or Hosting

This section explains exactly where to put your own domain, server IP, and hosting/proxy values.

Example values used below:

```text
Server IP:          203.0.113.10
Main website:       https://my-site.com
File manager URL:   https://files.my-site.com/test
Backend API URL:    https://files.my-site.com/api
```

These are examples only. Replace `my-site.com`, `files.my-site.com`, and `203.0.113.10` with your real values.

### 1. Domain DNS

This is not changed in repository files.

Open the DNS panel of your domain provider and create a record:

```text
Type: A
Name: files
Value: 203.0.113.10
```

After that, `files.my-site.com` points to the server where this Docker project runs.

### 2. Backend URL For The Built-In Frontend

Create a new local file in the project root:

```text
.env
```

Put this line into `.env`:

```env
NEXT_PUBLIC_API_URL=https://files.my-site.com/api
```

If you change backend `MAX_UPLOAD_SIZE_BYTES` in `.env.dev`, also add the same byte value to `.env` for browser-side validation:

```env
NEXT_PUBLIC_MAX_UPLOAD_SIZE_BYTES=52428800
```

Why this is a separate file: Docker Compose automatically reads `.env` for `${NEXT_PUBLIC_API_URL}` in `docker-compose.dev.yml`. This value is used while building the Next.js frontend. Do not commit `.env` if it contains real production values.

### 3. Allowed Website Domains For Backend

Open the existing file:

```text
.env.dev
```

Find or add this line:

```env
ALLOWED_ORIGINS=https://files.my-site.com
```

Use this value when users open the ready file manager page at `https://files.my-site.com/test`.

If your main website `https://my-site.com` has its own UI and calls this backend API directly, use:

```env
ALLOWED_ORIGINS=https://my-site.com
```

For multiple allowed sites, separate values with commas:

```env
ALLOWED_ORIGINS=https://files.my-site.com,https://my-site.com
```

### 4. Reverse Proxy Or Hosting Routes

Nginx is not included in this repository. It is configured on the server or in the hosting control panel.

If Nginx is installed on a Linux server, create a file outside the project, for example:

```text
/etc/nginx/sites-available/file-manager.conf
```

Put this config there and replace `files.my-site.com` with your real file manager domain:

```nginx
server {
    listen 80;
    server_name files.my-site.com;

    location /api/events {
        proxy_pass http://127.0.0.1:8000/events;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

If you use Caddy, Traefik, Cloudflare, or a hosting panel instead of Nginx, create the same routes there:

```text
https://files.my-site.com/      -> http://127.0.0.1:3000
https://files.my-site.com/api/  -> http://127.0.0.1:8000/
```

The backend API paths are then available as:

```text
https://files.my-site.com/api/files
https://files.my-site.com/api/alerts
https://files.my-site.com/api/events
```

### 5. Public Ports

You usually do not need to change ports in `docker-compose.dev.yml`.

Current public ports:

```yaml
frontend: 3000
backend: 8000
database for local access: 5433
```

Change `docker-compose.dev.yml` only if the server already uses these ports. Change the left side only:

```yaml
ports:
  - "8080:3000"
```

Then the frontend is available on host port `8080`, while the container still uses port `3000`.

### 6. Start After Changing Values

Rebuild the frontend after changing `NEXT_PUBLIC_API_URL`, because this value is embedded into the browser bundle:

```bash
docker compose -f docker-compose.dev.yml up --build
docker exec -it backend alembic upgrade head
```

Open:

```text
https://files.my-site.com/test
```

### 7. Connect From An Existing Website

If you want to use the ready UI, add a link or button on your existing website:

```text
https://files.my-site.com/test
```

If your existing website has its own UI, call the backend API directly:

```text
POST https://files.my-site.com/api/files
GET  https://files.my-site.com/api/files
GET  https://files.my-site.com/api/events
```

In that case, remember to allow the main website domain in `.env.dev`:

```env
ALLOWED_ORIGINS=https://my-site.com
```

### 8. If You Use Only Server IP Without Domain

For a quick test without DNS and without reverse proxy:

Project root `.env`:

```env
NEXT_PUBLIC_API_URL=http://203.0.113.10:8000
```

Existing `.env.dev`:

```env
ALLOWED_ORIGINS=http://203.0.113.10:3000
```

Open:

```text
http://203.0.113.10:3000/test
```

For production, prefer a domain with HTTPS and a reverse proxy.

## Configuration

Docker Compose reads backend environment variables from `.env.dev`.

The `.env.dev` file is intentionally committed with demo-only credentials so the project runs immediately after clone. If you replace these demo values with real server credentials, add `.env.dev` to `.gitignore` before any push. Treat real env values as access keys to your application and infrastructure, and never publish them to GitHub or similar cloud repositories.

Important backend variables:

| Variable | Description |
| --- | --- |
| `POSTGRES_HOST` | PostgreSQL host used by backend, worker, and beat. |
| `POSTGRES_PORT` | PostgreSQL port inside the Docker network. |
| `POSTGRES_DB` | PostgreSQL database name. |
| `POSTGRES_USER` | PostgreSQL user. |
| `POSTGRES_PASSWORD` | PostgreSQL password. |
| `PGSSLMODE` | PostgreSQL SSL mode. `disable` is used for local Docker networking. |
| `DATABASE_POOL_SIZE` | Base SQLAlchemy connection pool size per backend process. Default `10`. |
| `DATABASE_POOL_MAX_OVERFLOW` | Extra temporary SQLAlchemy connections allowed above the base pool size. Default `10`. |
| `DATABASE_POOL_RECYCLE_SECONDS` | SQLAlchemy connection lifetime before recycling. Default `1800` helps long-running web/worker processes avoid stale PostgreSQL connections. |
| `REDIS_URL` | Redis URL for Celery and SSE pub/sub. |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins allowed by backend CORS. |
| `MAX_FILE_SIZE_BYTES` | Business scan threshold: accepted files above this size are marked suspicious. |
| `MAX_UPLOAD_SIZE_BYTES` | Hard upload acceptance limit. Keep it greater than or equal to `MAX_FILE_SIZE_BYTES`; larger uploads return `413`. |
| `PROCESSING_TIMEOUT_SECONDS` | Age after which an in-progress file is considered stale. |
| `PROCESSING_RECOVERY_INTERVAL_SECONDS` | Celery Beat watchdog interval. |
| `MAX_PROCESSING_ATTEMPTS` | Retry limit before a file is marked as failed. |
| `DASHBOARD_EVENTS_CHANNEL` | Redis pub/sub channel for dashboard events. |
| `DASHBOARD_EVENTS_HEARTBEAT_SECONDS` | SSE keepalive interval. |
| `DASHBOARD_EVENTS_RETRY_TIMEOUT_MS` | Browser SSE retry hint. |
| `WORKER_METRICS_ENABLED` | Enable `/metrics` endpoint in worker/beat (`true`/`false`). |
| `WORKER_METRICS_PORT` | Metrics port for worker/beat metrics server (for example, `9101` and `9102`). |

Frontend configuration:

| Variable | Description |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Public backend URL used by the browser. Docker Compose sets it to `http://localhost:8000`. |
| `NEXT_PUBLIC_MAX_UPLOAD_SIZE_BYTES` | Public UI validation limit for file selection. Keep it aligned with backend `MAX_UPLOAD_SIZE_BYTES`. |

## Local Development

Backend:

```bash
cd backend
uv run --group dev pytest
uv run --group dev uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
uv run --group dev celery -A src.tasks.celery_app worker -l info
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run build
npm run dev
```

## Verification

Recommended checks before handoff:

```bash
cd backend
uv run --group dev pytest
uv run python -m compileall src tests
```

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Docker smoke checklist:

- Start the stack: `docker compose -f docker-compose.dev.yml up`.
- Run migrations in another terminal: `docker exec -it backend alembic upgrade head`.
- Check `/health/live`, `/health/ready`, `/docs`, `/metrics`, `/files`, `/alerts`, and `/events`.
- Upload a clean text file and verify it becomes `processed` and `clean`.
- Upload a suspicious extension such as `.sh` and verify it becomes `processed` and `suspicious`.
- Verify file download, title update, file deletion, 404 responses, and alert cascade deletion.
- If you enabled monitoring stack:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.monitoring.yml --profile monitoring up -d
```

- Verify observability endpoints:

  - Prometheus: [http://localhost:9090](http://localhost:9090)
  - Grafana: [http://localhost:3001](http://localhost:3001), login `admin`, password `admin`
  - Backend metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
  - Worker metrics: [http://localhost:9101/metrics](http://localhost:9101/metrics)
  - Beat metrics: [http://localhost:9102/metrics](http://localhost:9102/metrics)

The development Celery worker uses the `solo` pool so the embedded Prometheus endpoint reports task counters from the same process that executes jobs. For higher-throughput production workers using `prefork`, use Prometheus multiprocess mode or a dedicated Celery exporter.

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health/live` | Process liveness probe. |
| `GET` | `/health/ready` | Dependency readiness probe for DB + Redis. |
| `GET` | `/health` | Backward-compatible health alias. |
| `GET` | `/metrics` | Prometheus metrics endpoint (request, DB/Redis client, and business counters). |
| `GET` | `/files` | List uploaded files. |
| `POST` | `/files` | Upload a file. |
| `GET` | `/files/{file_id}` | Get one file. |
| `PATCH` | `/files/{file_id}` | Update file title. |
| `DELETE` | `/files/{file_id}` | Delete file and related alerts. |
| `GET` | `/files/{file_id}/download` | Download stored file content. |
| `GET` | `/alerts` | List processing alerts. |
| `GET` | `/events` | SSE stream with dashboard snapshot and patches. |

Suspicious files are still downloadable by design. The `requires_attention` flag and related alerts are an informational review layer; they warn operators about risk but do not quarantine or block stored file downloads.

## Production Deployment Guide

The standard Docker launch commands above are for local review and development. For production, keep the same application architecture but move runtime settings and infrastructure to the target environment.

Before publishing the application on a real domain:

- Point DNS to the server and put the frontend/backend behind HTTPS with a reverse proxy or hosting router.
- Store real secrets outside Git. Keep `.env.dev` demo values only for local clone-and-run usage, and put production credentials in the server environment, secret manager, or a private env file ignored by Git.
- Set frontend `NEXT_PUBLIC_API_URL` to the public backend URL, and set backend `ALLOWED_ORIGINS` to the exact frontend domain or domains.
- Use persistent storage for PostgreSQL data and uploaded files. Back up both the database and file storage together because metadata and binaries belong to the same file records.
- Prefer a dedicated production Dockerfile or Compose profile: remove `--reload`, run FastAPI as a non-root user, mount writable volumes with correct ownership, and keep Celery worker and beat running.
- Run `alembic upgrade head` as a controlled release step before serving the new backend version.
- Verify `/health`, `/docs`, `/files`, `/alerts`, and `/events` after deployment.

Do not expose the application to the public internet without authentication. Use the production auth guidance below before real users or external traffic can reach the service.

## Production Handoff Notes

This repository is ready for technical review and local Docker-based evaluation. For a real production deployment, replace local development settings with environment-specific configuration:

- Use strong database credentials and secrets outside the repository.
- Keep the review/dev Compose backend command without hot reload. If you add a separate hot-reload profile for local coding, do not use it for production.
- Keep PostgreSQL data and file storage on persistent volumes managed by the target environment.
- Run migrations as a controlled release step with `alembic upgrade head`.
- Set `NEXT_PUBLIC_API_URL` to the public backend URL.
- Put the frontend and backend behind HTTPS/reverse proxy infrastructure.
- Keep Celery worker and beat running as non-root users, as configured in the Docker Compose file.

### Docker Users And File Permissions

The development backend container intentionally keeps the default container user. In `docker-compose.dev.yml`, the backend service bind-mounts `./backend:/backend`; the application also creates uploaded files under `backend/storage/files`. Setting `USER nobody` on this dev FastAPI container can break writes to storage, bytecode/cache directories, or migration tooling on Windows/Linux host mounts.

The Compose backend command runs Uvicorn without `--reload` so the standard Docker startup is stable for long-lived SSE connections. If you want hot reload while coding, add it only in a local override/profile. The Celery worker and beat processes already drop privileges with `--uid nobody --gid nogroup`. For production, prefer a separate production Dockerfile/Compose profile: run FastAPI as a non-root user, mount writable volumes with correct ownership/permissions, and keep runtime storage outside the source bind mount.

### Authentication Required In Production

Before exposing this application on your own server, domain, or public network, protect the frontend and backend with authentication. Without an auth boundary, anyone who can reach the service can call `/files`, `/alerts`, `/events`, and `/files/{file_id}/download`. The `/events` stream sends realtime dashboard snapshots and patches with file metadata and alert details, so leaving it public can expose operational and document information.

Use one of these approaches before production traffic:

- For a single-admin or closed-team deployment, protect the whole domain at the reverse proxy or hosting layer: Nginx Basic Auth, Cloudflare Access, hosting access control, or private network access.
- For multi-user access, implement application auth: login/password, strongly hashed passwords, session cookies or JWT, user roles, and owner/team access checks for `/files`, `/alerts`, `/events`, and downloads.
- Do not treat a secret token embedded into frontend code as full protection. Anything shipped to the browser can be inspected by users.

The standard local Docker commands above remain unchanged. This authentication requirement applies when publishing the application to a real server, domain, or public network.

## Current Review Status

The project has been validated with backend tests, frontend typecheck/lint/build, Docker startup, migrations, Celery worker processing, SSE events, upload/download/update/delete flows, validation errors, and alert cleanup.
