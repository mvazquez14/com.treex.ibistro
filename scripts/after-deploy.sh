#! /usr/bin/env bash

# Exit in case of error
set -e

cd "$(dirname "$0")/.."

rm -f compose.override.yml
cp .envprod .env

docker compose -f compose.yml -f compose.deploy.yml --project-name ibistro-prd build --no-cache backend
docker compose -f compose.yml -f compose.deploy.yml --project-name ibistro-prd run --rm ensure-db
docker compose -f compose.yml -f compose.deploy.yml --project-name ibistro-prd up -d --no-deps --force-recreate redis backend
docker compose -f compose.yml -f compose.deploy.yml --project-name ibistro-prd run --rm backend bash scripts/prestart.sh
