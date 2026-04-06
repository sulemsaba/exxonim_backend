# exxonim_backend

Backend API for the Exxonim platform.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 async ORM
- asyncpg
- Alembic
- JWT auth helpers

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python scripts/seed_roles_permissions.py
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Local PostgreSQL

This machine already had another PostgreSQL server listening on `localhost:5432`,
so the project database runs on a separate local PostgreSQL 17 instance at
`localhost:5433`.

Default local database settings:

```text
Host: localhost
Port: 5433
Database: Exxonim
User: app_user
Password: strongpassword
```

Start and stop it with:

```text
Linux/local-first workflow:
- use the frontend monorepo helper at ../exxonim/scripts/setup-db.sh
- or start your local PostgreSQL service/cluster directly

Windows helper scripts:
- .\scripts\start-postgres.ps1
- .\scripts\stop-postgres.ps1
```

## Environment Variables

Copy `.env.example` to `.env` and update the values for your local machine.

## API

- Root: `GET /`
- Live health: `GET /health/live`
- Ready health: `GET /health/ready`
- Docs: `GET /docs`

## Auth And Bootstrap

- roles and permissions are seeded with `python scripts/seed_roles_permissions.py`
- the first superuser should be created by CLI, not by public signup
- CLI module: `python -m app.cli.superuser --email <email>`

## Project Structure

```text
nim_backend/
|-- alembic/
|-- app/
|   |-- core/
|   |-- crud/
|   |-- models/
|   |-- routers/
|   `-- schemas/
|-- scripts/
|-- .env.example
|-- requirements.txt
`-- README.md
```
