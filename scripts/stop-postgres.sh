#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${HOME}/.local/share/exxonim-postgres/data"

if [[ ! -f "${DATA_DIR}/PG_VERSION" ]]; then
  echo "PostgreSQL data directory not found."
  exit 0
fi

if ! pg_ctl -D "${DATA_DIR}" status >/dev/null 2>&1; then
  echo "PostgreSQL is not running."
  exit 0
fi

pg_ctl -D "${DATA_DIR}" stop -m fast
