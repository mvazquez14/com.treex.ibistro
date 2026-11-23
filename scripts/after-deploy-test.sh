#!/usr/bin/env bash
# iBistro — Test VPS (ibistro.test.treex.com.mx). Do not run on production.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .envtest ]]; then
  echo "ERROR: .envtest missing on server." >&2
  exit 1
fi

rm -f compose.override.yml
cp .envtest .env

docker network inspect traefik-public >/dev/null 2>&1 || docker network create traefik-public

compose=(docker compose -f compose.yml -f compose.deploy.yml --project-name ibistro-test)

echo "==> Building iBistro test (ibistro-test)"
"${compose[@]}" build backend
"${compose[@]}" run --rm ensure-db
"${compose[@]}" up -d --no-deps --force-recreate redis backend
"${compose[@]}" run --rm backend alembic upgrade head

echo "==> Checking whether this database still needs seed.py"
set +e
"${compose[@]}" run --rm -T backend python -c '
import asyncio
from sqlmodel import select
from app.core.db import async_session_maker
from app.models import ServiceCategory

async def needs_seed() -> bool:
    async with async_session_maker() as session:
        found = await session.exec(select(ServiceCategory).limit(1))
        return found.first() is None

raise SystemExit(0 if asyncio.run(needs_seed()) else 1)
'
status=$?
set -e
if [[ $status -eq 0 ]]; then
  echo "==> First deploy: running seed.py"
  "${compose[@]}" run --rm backend python app/seed.py
elif [[ $status -eq 1 ]]; then
  echo "==> Database already has categories; skipping seed.py"
else
  echo "ERROR: could not check the database (exit $status)." >&2
  exit "$status"
fi

echo "==> iBistro test deploy done."
"${compose[@]}" ps
