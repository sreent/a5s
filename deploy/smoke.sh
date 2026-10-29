#!/bin/sh
# Starts a5s's containers with stand-ins for the model, the identity provider
# and locked storage, then checks that a person must sign in, that a message
# runs end to end, that a worker reaches only the gateway, and that the ledger
# is copied, locked, and verifies against its copies.
# Needs the image first: docker build -t a5s:dev .
set -eu
cd "$(dirname "$0")/.."

env_file=$(mktemp)
reply=$(mktemp)
random() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9'; }
idp_password=$(random)
printf 'A5S_DB_PASSWORD=%s\nA5S_SERVICE_TOKEN=%s\nA5S_IDP_PASSWORD=%s\n' \
  "$(random)" "$(random)" "$idp_password" > "$env_file"
for part in GATEWAY CHANNELS SCHEDULER ANCHOR; do
  echo "A5S_DB_${part}_PASSWORD=$(random)" >> "$env_file"
done
echo "A5S_ANCHOR_STORE=s3://a5s-ledger/sample" >> "$env_file"
compose() { docker compose -p a5s-smoke --env-file "$env_file" -f deploy/compose.yaml \
              -f deploy/compose.stub.yaml -f deploy/compose.identity.yaml \
              -f deploy/compose.storage.yaml "$@"; }
trap 'compose down -v >/dev/null 2>&1; rm -f "$env_file" "$reply"' EXIT

compose up -d

sign_in() {  # a token from the stand-in identity provider
  curl -sf --retry 60 --retry-all-errors --retry-delay 2 \
    http://127.0.0.1:8180/realms/a5s/protocol/openid-connect/token \
    -d grant_type=password -d client_id=a5s-local -d scope=openid \
    -d username="$1" --data-urlencode password="$idp_password" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}
ana=$(sign_in ana)
ben=$(sign_in ben)

channel=http://127.0.0.1:8701/channels/local/messages
send() {  # prints the status, and writes the body to $reply
  curl -s -o "$reply" -w '%{http_code}' --retry 60 --retry-all-errors --retry-delay 1 \
    -X POST "$channel" -H 'content-type: application/json' "$@"
}

status=$(send -d '{"agent": "assistant", "text": "Hi"}')
[ "$status" = 401 ] || { echo "A message without a token got $status, not 401."; exit 1; }
status=$(send -H "authorization: Bearer $ben" -d '{"person": "ana", "agent": "assistant", "text": "Hi"}')
[ "$status" = 403 ] || { echo "Ben sending as Ana got $status, not 403."; exit 1; }
echo "A message needs a token, and the token must be the sender's."

status=$(send -H "authorization: Bearer $ana" \
  -d '{"agent": "assistant", "text": "Which questions mention an invoice?"}')
echo "Reply ($status): $(cat "$reply")"
grep -q "Q-1001" "$reply"

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
for host, port in (("postgres", 5432), ("keycloak", 8080), ("localstack", 4566),
                   ("api.deepseek.com", 443), ("1.1.1.1", 443)):
    assert not reach(host, port), f"the worker can reach {host}:{port}"
print("The worker holds no secrets, and reaches only the gateway.")
PY

compose exec -T scheduler python - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["A5S_DATABASE_URL"]) as conn:
    for statement in ("insert into inbound (id, channel, source_id, person, agent, text, reply_to) "
                      "values (gen_random_uuid(), 'teams', 'x', 'ben', 'assistant', 'hi', '{}')",
                      "update instances set level = 2", "truncate ledger"):
        try:
            conn.execute(statement)
        except psycopg.errors.InsufficientPrivilege:
            conn.rollback()
        else:
            raise AssertionError(f"the scheduler could run: {statement}")
print("The scheduler connects as its own role, and can't write the core's records.")
PY

compose exec -T gateway a5s ledger tail -n 50 | grep -q '"identity": "verified"'
echo "The core checked Ana's identity itself, and recorded it."
compose exec -T anchor a5s anchor
compose exec -T anchor python - <<'PY'
import boto3
s3 = boto3.client("s3")
versions = s3.list_object_versions(Bucket="a5s-ledger", Prefix="sample/segments/")["Versions"]
for v in versions:
    try:
        s3.delete_object(Bucket="a5s-ledger", Key=v["Key"], VersionId=v["VersionId"])
    except s3.exceptions.ClientError as exc:
        assert exc.response["Error"]["Code"] == "AccessDenied", exc
    else:
        raise AssertionError(f"{v['Key']} could be deleted")
print(f"The ledger's {len(versions)} copies are locked: deleting them is refused.")
PY
compose exec -T anchor a5s ledger verify
echo "Smoke test passed."
