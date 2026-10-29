#!/bin/sh
# Starts a5s's containers with a stand-in model, then checks that a message
# runs end to end, that a worker reaches only the gateway, and that the ledger
# verifies. Needs the image first: docker build -t a5s:dev .
set -eu
cd "$(dirname "$0")/.."

env_file=$(mktemp)
random() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9'; }
printf 'A5S_DB_PASSWORD=%s\nA5S_SERVICE_TOKEN=%s\n' "$(random)" "$(random)" > "$env_file"
compose() { docker compose -p a5s-smoke --env-file "$env_file" \
              -f deploy/compose.yaml -f deploy/compose.stub.yaml "$@"; }
trap 'compose down -v >/dev/null 2>&1; rm -f "$env_file"' EXIT

compose up -d
reply=$(curl -sf --retry 60 --retry-all-errors --retry-delay 1 \
  -X POST http://127.0.0.1:8701/channels/local/messages -H 'content-type: application/json' \
  -d '{"person": "ana", "agent": "assistant", "text": "Which questions mention an invoice?"}')
echo "Reply: $reply"
echo "$reply" | grep -q "Q-1001"

compose exec -T worker python - <<'PY'
import os, socket
secrets = [k for k in os.environ if any(w in k for w in ("TOKEN", "PASSWORD", "DATABASE", "API_KEY"))]
assert not secrets, f"the worker holds secrets: {secrets}"
def reach(host, port):
    try:
        socket.create_connection((host, port), timeout=3).close()
        return True
    except OSError:
        return False
assert reach("gateway", 8700), "the worker can't reach the gateway"
for host, port in (("postgres", 5432), ("api.deepseek.com", 443), ("1.1.1.1", 443)):
    assert not reach(host, port), f"the worker can reach {host}:{port}"
print("The worker holds no secrets, and reaches only the gateway.")
PY

compose exec -T gateway a5s ledger verify | tee /dev/stderr | grep -q "ok=True"
echo "Smoke test passed."
