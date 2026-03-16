# exxonim_backend

Phase 0 backend scaffold for the Exxonim platform.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 async ORM
- asyncpg
- Alembic
- JWT auth helpers

## Quick Start

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
.\scripts\start-postgres.ps1
alembic upgrade head
uvicorn app.main:app --reload
```

## Local PostgreSQL

This machine already had another PostgreSQL server listening on `localhost:5432`,
so the project database runs on a separate local PostgreSQL 17 instance at
`localhost:5433`.

Default local database settings:

```text
Host: localhost
Port: 5433
Database: marketing_site_dev
User: app_user
Password: strongpassword
```

Start and stop it with:

```powershell
.\scripts\start-postgres.ps1
.\scripts\stop-postgres.ps1
```

## Environment Variables

Copy `.env.example` to `.env` and update the values for your local machine.

## API

- Root: `GET /`
- Health: `GET /api/v1/health`
- Docs: `GET /docs`

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
