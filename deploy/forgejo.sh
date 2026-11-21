#!/bin/sh
# The read-only repository adapter against a real, disposable Forgejo, on synthetic data alone.
# Starts and removes its own containers; Python never needs to call Docker. With
# A5S_TEST_FORGEJO_LIVE=required, also runs the real-model gateway case through an a5s worker.
set -eu
cd "$(dirname "$0")/.."
FORGEJO_IMAGE=codeberg.org/forgejo/forgejo:12.0@sha256:dbb0f88677f0c65cd1b66fb83504225aa5a04c4bc4a5ffdf9fc9a3a6d5bb1c68
POSTGRES_IMAGE=postgres:16@sha256:1beaa3084eee2676f20a9cd9928f0bf2c5bf674f8e49f81017912183d377c61c
name=${A5S_TEST_FORGEJO_CONTAINER:-a5s-forgejo-test}
port=${A5S_TEST_FORGEJO_PORT:-3300}
db_port=${A5S_TEST_FORGEJO_DB_PORT:-55433}
worker_port=${A5S_TEST_FORGEJO_WORKER_PORT:-18723}
gateway_port=${A5S_TEST_FORGEJO_GATEWAY_PORT:-18081}
password=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')
cleanup() {
  docker rm -f "$name" "$name-postgres" "$name-worker" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
docker run -d --name "$name" -p "127.0.0.1:$port:3000" \
  -e FORGEJO__security__INSTALL_LOCK=true \
  -e FORGEJO__service__DISABLE_REGISTRATION=true \
  -e FORGEJO__server__ROOT_URL="http://127.0.0.1:$port/" \
  -e FORGEJO__database__DB_TYPE=sqlite3 "$FORGEJO_IMAGE" >/dev/null
for _ in $(seq 60); do
  if curl -fsS "http://127.0.0.1:$port/api/v1/version" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:$port/api/v1/version" >/dev/null
docker exec -u git "$name" forgejo admin user create --admin --username pilot-admin \
  --password "$password" --email pilot-admin@a5s.test --must-change-password=false >/dev/null
status=0
if [ "${A5S_TEST_FORGEJO_LIVE:-}" = required ]; then
  docker run -d --name "$name-postgres" -e POSTGRES_USER=a5s -e POSTGRES_HOST_AUTH_METHOD=trust \
    -p "127.0.0.1:$db_port:5432" "$POSTGRES_IMAGE" >/dev/null
  for _ in $(seq 60); do
    if docker exec "$name-postgres" pg_isready -U a5s >/dev/null 2>&1; then break; fi
    sleep 1
  done
  docker build -t a5s:dev .
  docker run -d --name "$name-worker" --add-host host.docker.internal:host-gateway \
    -p "127.0.0.1:$worker_port:8702" \
    -e A5S_GATEWAY_URL="http://host.docker.internal:$gateway_port" \
    a5s:dev worker --host 0.0.0.0 >/dev/null
  for _ in $(seq 60); do
    if curl -fsS "http://127.0.0.1:$worker_port/openapi.json" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  A5S_TEST_FORGEJO_URL="http://127.0.0.1:$port" A5S_TEST_FORGEJO_ADMIN_PASSWORD="$password" \
    A5S_TEST_DATABASE_URL="postgresql://a5s@127.0.0.1:$db_port/postgres" A5S_REGRESSION=required \
    A5S_TEST_WORKER_IMAGE=a5s:dev A5S_TEST_WORKER_URL="http://127.0.0.1:$worker_port" \
    A5S_TEST_WORKER_GATEWAY="http://host.docker.internal:$gateway_port" A5S_TEST_BRIDGE=0.0.0.0 \
    uv run --env-file .a5s/live.env pytest -q -m forgejo tests/test_forgejo.py "$@" || status=$?
else
  A5S_TEST_FORGEJO_URL="http://127.0.0.1:$port" A5S_TEST_FORGEJO_ADMIN_PASSWORD="$password" \
    uv run pytest -q -m forgejo tests/test_forgejo.py "$@" || status=$?
fi
if [ "$status" -ne 0 ]; then docker logs --tail 30 "$name"; fi
exit "$status"
