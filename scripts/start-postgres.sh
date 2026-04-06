#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${HOME}/.local/share/exxonim-postgres"
DATA_DIR="${DATA_ROOT}/data"
LOG_FILE="${DATA_ROOT}/server.log"

mkdir -p "${DATA_ROOT}"

if [[ ! -f "${DATA_DIR}/PG_VERSION" ]]; then
  initdb -D "${DATA_DIR}" -U postgres --auth-local=trust --auth-host=trust
fi

if pg_ctl -D "${DATA_DIR}" status >/dev/null 2>&1; then
  echo "PostgreSQL is already running."
  exit 0
fi

pg_ctl \
  -D "${DATA_DIR}" \
  -l "${LOG_FILE}" \
  -o "-p 5433 -k ${DATA_ROOT}" \
  start -w
