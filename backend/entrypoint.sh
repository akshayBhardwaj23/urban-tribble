#!/bin/sh
set -e

# Migrate once before the server process starts, then serve with a single
# worker so the in-process upload ThreadPoolExecutor is not split.
if [ "${RUN_MIGRATIONS_ON_STARTUP:-true}" = "true" ]; then
  alembic upgrade head
fi

export RUN_MIGRATIONS_ON_STARTUP=false
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
