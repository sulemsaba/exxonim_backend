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
alembic upgrade head
uvicorn app.main:app --reload
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
├── alembic/
├── app/
│   ├── core/
│   ├── crud/
│   ├── models/
│   ├── routers/
│   └── schemas/
├── .env.example
├── requirements.txt
└── README.md
```

