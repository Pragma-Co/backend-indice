# API-6 — Backend

Backend service for the API-6 college project. Everything runs inside Docker, so the whole team gets the exact same environment on Linux, Windows and macOS — no local Python or database installation required.

## Tech stack

| Technology | Version | Role |
|------------|---------|------|
| [Python](https://www.python.org/) | 3.12 | Language (inside the container) |
| [Django](https://www.djangoproject.com/) | 5.2 LTS | Web framework / API |
| [PostgreSQL](https://www.postgresql.org/) | 17 | Relational database |
| [MongoDB](https://www.mongodb.com/) | 8.2 | Non-relational (document) database |
| [Docker Compose](https://docs.docker.com/compose/) | v2 | Orchestrates all services |

Django talks to PostgreSQL through its native ORM (`psycopg`) and to MongoDB through `pymongo` (see `core/mongo.py`). The frontend (Vue.js) lives in a separate repository and consumes this API — CORS is enabled only for the origins listed in `DJANGO_CORS_ALLOWED_ORIGINS` (the Vite dev server, by default).

## Requirements

**Software**

- Docker Engine **24.0+** with the Compose plugin **v2.20+** (Linux), or
- Docker Desktop **4.30+** (Windows/macOS). On Windows, use the **WSL2 backend** (default).
- Git

**Hardware (minimum)**

- 2 CPU cores (4 recommended)
- 4 GB RAM (8 GB recommended on Windows, since WSL2 shares memory with the host)
- ~5 GB of free disk space (images + database volumes)

Check your versions:

```bash
docker --version          # Docker version 24.0.0 or newer
docker compose version    # Docker Compose version v2.20 or newer
```

## What is inside the Docker setup

`docker-compose.yml` defines three services:

| Service | Container | Image | Purpose |
|---------|-----------|-------|---------|
| `api` | `api6-django` | built from `Dockerfile` (python:3.12-slim) | Django application, auto-runs migrations on start |
| `postgres` | `api6-postgres` | postgres:17-alpine | Relational database |
| `mongodb` | `api6-mongodb` | mongo:8.2 | Document database |

- Database data is persisted in named volumes (`postgres_data`, `mongo_data`), so containers can be recreated without losing data.
- The project source is bind-mounted into the `api` container — code changes reload automatically, no rebuild needed.
- The `api` service only starts after both databases pass their health checks.

## Installation (step by step)

**1. Clone the repository**

```bash
git clone https://github.com/Pragma-Co/backend-api-6.git
cd FATEC-API-6-Semestre/backend
```

**2. Generate your environment file**

One command creates your `.env` with strong random secrets and a `CREDENTIALS.txt` copy of them (no local Python needed — it runs through Docker):

```bash
# Linux/macOS
docker run --rm --user "$(id -u):$(id -g)" -v "$(pwd):/app" -w /app python:3.12-slim python scripts/setup_env.py

# Windows (PowerShell)
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim python scripts/setup_env.py
```

The script refuses to overwrite an existing `.env`. To regenerate everything, add `--force` — and note that already-initialized databases keep their old passwords, so a regeneration also requires `docker compose down -v` (which deletes all database data).

<details>
<summary>Prefer to do it by hand?</summary>

Copy the template and replace every `<...>` placeholder with a random value:

```bash
# Linux/macOS
cp .env.example .env
openssl rand -hex 16        # passwords (use -hex 32 for DJANGO_SECRET_KEY)

# Windows (PowerShell)
Copy-Item .env.example .env
-join (1..32 | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })   # use 1..64 for DJANGO_SECRET_KEY
```

</details>

> **LGPD notice:** `.env` and `CREDENTIALS.txt` hold real credentials and are ignored by Git. Save the passwords in a password manager, then **delete `CREDENTIALS.txt`**. Never commit these files or paste their contents in chats/issues.

**3. Build and start everything**

```bash
docker compose up --build
```

The first run downloads images and builds the app (a few minutes). Subsequent runs are much faster. Add `-d` to run in the background.

**4. Verify it works**

Open <http://localhost:8000/health/> — you should see both databases connected:

```json
{
  "project": "API-6",
  "status": "ok",
  "databases": {
    "postgresql": {"connected": true, "version": "PostgreSQL 17.x"},
    "mongodb": {"connected": true, "version": "8.2.x"}
  }
}
```

**5. Log in to the Django admin**

A default superuser is created automatically on the first start, using `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` from your `.env`. Just open <http://localhost:8000/admin/> and log in with those values.

To add more users later: `docker compose exec api python manage.py createsuperuser`.

## URLs

| URL | Description |
|-----|-------------|
| <http://localhost:8000/> | API root (welcome + endpoint list) |
| <http://localhost:8000/health/> | Health check: PostgreSQL + MongoDB connectivity |
| <http://localhost:8000/projects/> | Active projects (JSON, read-only) — see [API endpoints](#api-endpoints) |
| <http://localhost:8000/disciplines/> | Active disciplines (JSON, read-only) — see [API endpoints](#api-endpoints) |
| <http://localhost:8000/admin/> | Django admin panel |
| `localhost:5433` | PostgreSQL (localhost only, e.g. for DBeaver/pgAdmin) |
| `localhost:27018` | MongoDB (localhost only, e.g. for Compass) |

> These are the default ports. If you changed `API_PORT`, `POSTGRES_PORT` or `MONGO_PORT` in your `.env`, use those instead.

## API endpoints

The Vue frontend calls the API through the Vite dev-server proxy: the browser requests `/api/projects/` and the proxy strips the `/api` prefix, so Django receives `/projects/`. That is why the routes live at the root, next to `/health/`.

All endpoints below are **read-only** (`GET` only — any other method answers `405 Method Not Allowed`), return `application/json`, list **only active records** (`active=true`) and are **ordered by name**. On an unexpected failure they answer `500` with `{"error": "<ExceptionName>"}`; details go to the server log only (no hosts, credentials or stack traces in the response).

### `GET /projects/`

Projects available in the **Projeto Associado** select of the metadata form. `code` is the first part of the document code (`PJT001-TUB-REV-REV01`).

```json
[
  { "id": 1, "code": "PJT001", "name": "Projeto Alfa" },
  { "id": 2, "code": "PJT002", "name": "Projeto Beta" }
]
```

### `GET /disciplines/`

Disciplines available in the **Disciplina** select. `acronym` is always the **first three letters of the name, upper-cased and without accents** (`Tubulação` → `TUB`, `Memória de Cálculo` → `MEM`); it is generated automatically when a discipline is saved without one and must match `^[A-Z]{3}$`.

```json
[
  { "id": 5, "acronym": "TUB", "name": "Tubulação" },
  { "id": 1, "acronym": "ENG", "name": "Engenharia" }
]
```

### Seeding the catalogs (development data)

Both catalogs start empty. Load the default development entries with the `seed_catalogs` command, run **inside the `api` container**:

```bash
docker compose exec api python manage.py seed_catalogs
```

It is idempotent: run it as many times as you like, it only creates what is missing (matched by project code / discipline name) and never overwrites edits made through the admin. It creates:

| Catalog | Entries |
|---------|---------|
| Projetos | `PJT001 - Projeto Alfa`, `PJT002 - Projeto Beta`, `PJT003 - Projeto Gama` |
| Disciplinas | Engenharia (`ENG`), Manufatura (`MAN`), Qualidade (`QUA`), Configuração (`CON`), Tubulação (`TUB`), Estrutura (`EST`), Elétrica (`ELE`) |

Projects and disciplines can also be managed through the Django admin (<http://localhost:8000/admin/>).

## Useful commands

```bash
# Lifecycle
docker compose up -d              # start everything in the background
docker compose down               # stop everything (data is kept)
docker compose down -v            # stop AND DELETE all database data (careful!)
docker compose restart api        # restart only Django
docker compose ps                 # list running services
docker compose logs -f api        # follow Django logs (also: postgres, mongodb)
docker compose up -d --build      # rebuild after changing requirements.txt/Dockerfile

# Django
docker compose exec api python manage.py migrate           # apply migrations
docker compose exec api python manage.py makemigrations    # create migrations
docker compose exec api python manage.py createsuperuser   # create an EXTRA admin user (the default one is automatic)
docker compose exec api python manage.py shell             # Django shell
docker compose exec api python manage.py test              # run tests
docker compose exec api python manage.py seed_catalogs     # load default projects/disciplines (idempotent)

# Databases
docker compose exec postgres psql -U api6_admin -d api6                                  # PostgreSQL shell
docker compose exec mongodb mongosh -u api6_admin -p --authenticationDatabase admin api6 # MongoDB shell
```

## LGPD & security notes

This project handles personal data topics this semester, so the environment was configured with LGPD in mind:

- **No default passwords** — passwords are randomly generated per machine and injected via environment variables (usernames use the shared default `api6_admin`).
- **Secrets never reach Git or Docker images** — `.env` and `CREDENTIALS.txt` are in `.gitignore` and `.dockerignore`.
- **PostgreSQL** enforces `scram-sha-256` password authentication (no `trust`, no `md5`).
- **MongoDB** runs with mandatory authentication (no anonymous access).
- **Nothing is exposed to the network** — the API (8000) and both databases (5433/27018) are bound to `127.0.0.1` only; other machines on your LAN cannot reach them.
- **Health/error responses never include connection details** — database failures are logged server-side; HTTP responses carry no usernames, hosts or stack traces.
- **Team rules:** never commit `.env`, never log or seed real personal data, rotate credentials if they leak, and collect only the data the application actually needs (data minimization).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `port is already allocated` | Another service uses the port. Set `API_PORT`, `POSTGRES_PORT` or `MONGO_PORT` to a free port in `.env` — these change only the host side; containers keep talking to each other on the internal defaults. |
| `password authentication failed` after editing `.env` | The database volume was initialized with the old password. Run `docker compose down -v && docker compose up -d` (deletes data). |
| Weird `\r` / `no such file` errors on Windows | Line-ending issue. `.gitattributes` already forces LF; re-clone or run `git rm --cached -r . && git reset --hard`. |
| Containers keep restarting | Check `docker compose logs -f` — usually a wrong value in `.env`. |
| MongoDB exits with a "kernel incompatibility" fatal log | MongoDB 8.0 does not start on Linux kernel 6.19+. This project pins `mongo:8.2`, which is fixed — do not downgrade the image. |
| Slow on Windows | Keep the project inside the WSL2 filesystem (e.g. `\\wsl$/Ubuntu/home/...`), not on `C:\`. |
| CORS error in the browser console | The frontend origin is not allowed. Add it to `DJANGO_CORS_ALLOWED_ORIGINS` in `.env` and restart: `docker compose restart api`. |

## Project structure

```
backend/
├── docker-compose.yml   # Service orchestration (api + postgres + mongodb)
├── Dockerfile           # Django application image
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template (source for scripts/setup_env.py)
├── scripts/             # setup_env.py — generates .env + CREDENTIALS.txt
├── manage.py            # Django CLI
├── api6/                # Django project (settings, URLs, WSGI/ASGI)
└── core/                # Main app, organized by layer
    ├── models/          # Relational entities (Project, Discipline)
    ├── views/           # HTTP endpoints (health, catalogs)
    ├── services/        # Business rules (acronym generation, catalog queries)
    ├── serializers/     # Model -> JSON conversion
    ├── tests/           # Test suite (Given/When/Then)
    ├── migrations/      # Database history
    ├── management/      # Commands: ensure_superuser, seed_catalogs
    ├── admin.py         # Django admin registrations
    ├── urls.py          # App routes (/projects/, /disciplines/)
    └── mongo.py         # Shared MongoDB client
```
