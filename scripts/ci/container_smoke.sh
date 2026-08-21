#!/usr/bin/env bash
set -euo pipefail

image=${1:?image name required}
port=${PORT:-18080}
container=${CONTAINER_NAME:-pasticuan-ci-smoke}
docker run --detach --rm --name "$container" --publish "$port:$port" \
  --env TELEGRAM_BOT_TOKEN=000000000:ci-smoke-token \
  --env TELEGRAM_WEBHOOK_SECRET=ci-smoke-secret \
  --env PORT="$port" --env UVICORN_LIFESPAN=off "$image" >/dev/null
cleanup() { docker rm --force "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
for _ in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${port}/" >/dev/null \
      && curl --fail --silent "http://127.0.0.1:${port}/ready" >/dev/null; then
    exit 0
  fi
  sleep 1
done
docker logs "$container" >&2 || true
exit 1
