#!/bin/sh
# The read-only repository adapter against a real, disposable Forgejo, on synthetic data alone.
# Starts and removes its own container; Python never needs to call Docker.
set -eu
cd "$(dirname "$0")/.."
FORGEJO_IMAGE=codeberg.org/forgejo/forgejo:12.0@sha256:dbb0f88677f0c65cd1b66fb83504225aa5a04c4bc4a5ffdf9fc9a3a6d5bb1c68
name=${A5S_TEST_FORGEJO_CONTAINER:-a5s-forgejo-test}
port=${A5S_TEST_FORGEJO_PORT:-3300}
password=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
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
A5S_TEST_FORGEJO_URL="http://127.0.0.1:$port" A5S_TEST_FORGEJO_ADMIN_PASSWORD="$password" \
  uv run pytest -q -m forgejo tests/test_forgejo.py "$@" || status=$?
if [ "$status" -ne 0 ]; then docker logs --tail 30 "$name"; fi
exit "$status"
