#!/bin/sh
# Starts a5s's containers with stand-ins for the model, the identity provider, a
# Matrix homeserver and locked storage, then checks that the core runs only a
# release its people approved, that a person must sign in, that a message runs end
# to end from the command line and from Matrix, that the core works obligations out
# from the records, that a worker reaches only the gateway, that an instance approver
# approves new settings where she works, and that the ledger is copied, locked, and
# verifies against its copies.
# Needs the image first: docker build -t a5s:dev .
# With --keep, it leaves the stack running afterwards, to try the web chat and Matrix.
set -eu
cd "$(dirname "$0")/.."
keep=$([ "${1:-}" = --keep ] && echo 1 || echo 0)

env_file=$(mktemp)
reply=$(mktemp)
work=$(mktemp -d)
chmod a+rx "$work"  # for the containers that sign and record the release
random() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9'; }
idp_password=$(random)
printf 'A5S_DB_PASSWORD=%s\nA5S_SERVICE_TOKEN=%s\nA5S_IDP_PASSWORD=%s\n' \
  "$(random)" "$(random)" "$idp_password" > "$env_file"
for part in GATEWAY CHANNELS SCHEDULER ANCHOR; do
  echo "A5S_DB_${part}_PASSWORD=$(random)" >> "$env_file"
done
echo "A5S_ANCHOR_STORE=s3://a5s-ledger/sample" >> "$env_file"
echo "A5S_SEAL_KEYS=$(random)" >> "$env_file"
python3 deploy/matrix/configure.py "$work/matrix" >> "$env_file"
compose() { docker compose -p a5s-smoke --env-file "$env_file" -f deploy/compose.yaml \
              -f deploy/compose.stub.yaml -f deploy/compose.identity.yaml \
              -f deploy/compose.storage.yaml -f deploy/compose.matrix.yaml "$@"; }
trap 'compose down -v >/dev/null 2>&1; rm -rf "$env_file" "$reply" "$work"' EXIT

compose up -d

# The core runs only a release this deployment's people approved. Here they're the
# sample's made-up people, whose keys are in the repository; a real deployment's
# approvers sign with keys only they hold.
if compose exec -T gateway a5s release status > "$reply" 2>&1; then
  echo "The core would run a release nobody here approved."; exit 1
fi
grep -q "nobody here has approved it yet" "$reply"
compose exec -T gateway a5s release show > "$work/release.yaml"
for person in priya tomas rosa kofi; do
  docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/scenarios/sample/keys:/keys:ro" \
    -v "$work:/work" -w /work "${A5S_IMAGE:-a5s:dev}" release sign --as "$person" --key "/keys/$person.key"
done
compose run --rm -T -v "$work:/work" -w /work setup release approve > /dev/null
compose exec -T gateway a5s release status | tail -1
echo "The core waited for the release to be approved here, by the people its changes need."

sign_in() {  # a token from the stand-in identity provider
  curl -sf --retry 60 --retry-all-errors --retry-delay 2 \
    http://127.0.0.1:8180/realms/a5s/protocol/openid-connect/token \
    -d grant_type=password -d client_id=a5s-local -d scope=openid \
    -d username="$1" --data-urlencode password="$idp_password" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}
ana=$(sign_in ana)
ben=$(sign_in ben)

channel=http://127.0.0.1:8703/channels/local/messages
send() {  # prints the status, and writes the body to $reply
  curl -s -o "$reply" -w '%{http_code}' --retry 60 --retry-all-errors --retry-delay 1 \
    -X POST "$channel" -H 'content-type: application/json' "$@"
}
field() { python3 -c "import json, sys; print(json.load(open(sys.argv[1]))$1)" "$reply"; }

status=$(send -d '{"agent": "assistant", "text": "Hi"}')
[ "$status" = 401 ] || { echo "A message without a token got $status, not 401."; exit 1; }
status=$(send -H "authorization: Bearer $ben" -d '{"person": "ana", "agent": "assistant", "text": "Hi"}')
[ "$status" = 403 ] || { echo "Ben sending as Ana got $status, not 403."; exit 1; }
echo "A message needs a token, and the token must be the sender's."

curl -sf -o "$reply" -D "$work/headers" http://127.0.0.1:8703/chat/
grep -qi "content-security-policy: default-src 'none'" "$work/headers"
curl -sf -o "$reply" http://127.0.0.1:8703/chat/config
field '["signin"]["authorization_endpoint"]' | grep -q "^http://127.0.0.1:8180/realms/a5s/"
status=$(curl -s -o "$reply" -w '%{http_code}' -X POST http://127.0.0.1:8703/chat/token \
  -H 'content-type: application/json' \
  -d '{"grant_type": "authorization_code", "code": "made-up", "code_verifier": "made-up",
       "redirect_uri": "http://127.0.0.1:8703/chat/"}')
[ "$status" = 400 ] || { echo "Passing on a made-up sign-in code got $status, not 400."; exit 1; }
field '["error"]' | grep -q invalid_grant
echo "The web chat sends people to Keycloak to sign in, and the core passes their code on to it."

status=$(send -H "authorization: Bearer $ana" \
  -d '{"agent": "assistant", "text": "Which questions mention an invoice?"}')
[ "$status" = 202 ] || { echo "Ana's message got $status, not 202."; exit 1; }
curl -sf -o "$reply" -H "authorization: Bearer $ana" \
  "$channel/$(field '["message"]')?wait=120"
echo "Reply: $(field '["replies"]')"
grep -q "Q-1001" "$reply"

# The same question from Ana's own Matrix account, in a direct chat with the assistant
for person in ana ben chen; do
  compose exec -T synapse register_new_matrix_user -c /config/homeserver.yaml -u "$person" \
    -p "$idp_password" --no-admin http://localhost:8008 > /dev/null
done
A5S_PASSWORD="$idp_password" python3 - <<'PY'
import json, os, time, uuid
from urllib.parse import quote
from urllib.request import Request, urlopen

HOMESERVER, BOT = "http://127.0.0.1:8008/_matrix/client/v3", "@a5s-assistant:a5s.test"

def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {token}"} if token else {})
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(HOMESERVER + path, data, headers, method=method), timeout=30) as answer:
        return json.load(answer)

def until(what, found, seconds=120):
    for _ in range(seconds):
        if result := found():
            return result
        time.sleep(1)
    raise SystemExit(f"In Matrix, {what} didn't happen within {seconds} seconds.")

ana = call("POST", "/login", {"type": "m.login.password", "password": os.environ["A5S_PASSWORD"],
                               "identifier": {"type": "m.id.user", "user": "ana"}})["access_token"]
room = call("POST", "/createRoom", {"is_direct": True, "invite": [BOT], "preset": "trusted_private_chat"},
            ana)["room_id"]
at = f"/rooms/{quote(room, safe='')}"
until("the assistant joining Ana's chat", lambda: BOT in call("GET", f"{at}/joined_members", token=ana)["joined"])
call("PUT", f"{at}/send/m.room.message/{uuid.uuid4().hex}",
     {"msgtype": "m.text", "body": "Which questions mention an invoice?"}, ana)
said = until("the assistant answering", lambda: [
    e["content"]["body"] for e in call("GET", f"{at}/messages?dir=b&limit=20", token=ana)["chunk"]
    if e["sender"] == BOT and e["type"] == "m.room.message"])
print(f"Reply in Matrix: {said[0]}")
assert "Q-1001" in said[0], said
PY
compose exec -T gateway a5s ledger tail -n 200 | grep -q '"identity": "verified by matrix"'
echo "The homeserver vouched for Ana in Matrix, and the core recorded it."

curl -sf -o "$reply" -H "authorization: Bearer $ana" http://127.0.0.1:8703/channels/local/inbox
field '["messages"]' > /dev/null  # reminders and escalations, which the clock decides
compose exec -T gateway python - <<'PY'
import os, time, psycopg
expected = [("Q-1001", "ana", "assistant-finance"), ("Q-1002", "ben", "assistant-finance"),
            ("Q-1003", "chen", None)]
for _ in range(60):  # the scheduler asks the core what's due every minute
    with psycopg.connect(os.environ["A5S_DATABASE_URL"]) as conn:
        owed = conn.execute("select record, person, instance_id from obligations "
                            "where done_at is null order by record").fetchall()
    if owed == expected:
        break
    time.sleep(2)
assert owed == expected, owed
print("The core worked the obligations out from the records, each naming who acts on it.")
with psycopg.connect(os.environ["A5S_DATABASE_URL"]) as conn:
    running = conn.execute("select id, status from instances order by id").fetchall()
assert running == [("assistant-finance", "active"), ("watcher-finance", "active")], running
print("The assistant and the watcher are both at work, in the release their people approved.")
PY

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
for host, port in (("postgres", 5432), ("channels", 8703), ("keycloak", 8080), ("synapse", 8008),
                   ("localstack", 4566), ("api.deepseek.com", 443), ("1.1.1.1", 443)):
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

# An instance approver approves a new version of the settings where she works. a5s asks her
# in the Matrix chat she last wrote in, and she approves on the core's page, having signed in
# afresh at Keycloak for that version alone.
compose exec -T gateway python - <<'PY'
import subprocess
from pathlib import Path
import yaml
settings = yaml.safe_load(Path("scenarios/sample/settings.yaml").read_text())
settings["instances"]["assistant-finance"]["serves"].append("chen")
Path("/tmp/next.yaml").write_text(yaml.safe_dump({**settings, "serial": settings["serial"] + 1}))
subprocess.run(["a5s", "propose", "--file", "/tmp/next.yaml"], check=True)
PY
A5S_PASSWORD="$idp_password" python3 - <<'PY'
import base64, hashlib, html, json, os, re, secrets, time
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener, urlopen

HOMESERVER, CORE = "http://127.0.0.1:8008/_matrix/client/v3", "http://127.0.0.1:8703"

def call(url, body=None, token=None, method=None):
    headers = {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {token}"} if token else {})
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(url, data, headers, method=method), timeout=30) as answer:
        return json.load(answer)

ana = call(f"{HOMESERVER}/login", {"type": "m.login.password", "password": os.environ["A5S_PASSWORD"],
                                     "identifier": {"type": "m.id.user", "user": "ana"}})["access_token"]
[room] = call(f"{HOMESERVER}/joined_rooms", token=ana)["joined_rooms"]
for _ in range(60):
    said = [e["content"]["body"] for e in call(f"{HOMESERVER}/rooms/{quote(room, safe='')}/messages"
                                               f"?dir=b&limit=20", token=ana)["chunk"]
            if e["type"] == "m.room.message" and "/approve/?settings=" in e["content"].get("body", "")]
    if said:
        break
    time.sleep(1)
else:
    raise SystemExit("a5s didn't ask Ana to approve the settings in her Matrix chat.")
link = re.search(r"http\S+/approve/\?settings=[0-9a-f]{64}", said[0]).group(0)
version = parse_qs(urlsplit(link).query)["settings"][0]
print(f"Asked in Matrix: {said[0].splitlines()[0]}")

class Stay(HTTPRedirectHandler):  # keep Keycloak's redirect back, to read the code in it
    def redirect_request(self, *args, **kwargs):
        return None

def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

jar = CookieJar()
browser = build_opener(HTTPCookieProcessor(jar), Stay)
salt, verifier, back = secrets.token_urlsafe(32), secrets.token_urlsafe(32), f"{CORE}/approve/"
signin = call(f"{CORE}/approve/config")["signin"]
page = browser.open(signin["authorization_endpoint"] + "?" + urlencode({
    "response_type": "code", "client_id": signin["client_id"], "redirect_uri": back,
    "scope": signin["scope"], "state": "s", "max_age": "0", "code_challenge_method": "S256",
    "nonce": b64(hashlib.sha256(f"a5s approves settings {version} {salt}".encode()).digest()),
    "code_challenge": b64(hashlib.sha256(verifier.encode()).digest())}), timeout=30).read().decode()
for cookie in jar:  # Keycloak's are Secure, which browsers send to 127.0.0.1 all the same
    cookie.secure = False
form = re.search(r'<form[^>]*id="kc-form-login"[^>]*>', page).group(0)
try:
    browser.open(Request(html.unescape(re.search(r'action="([^"]+)"', form).group(1)), urlencode(
        {"username": "ana", "password": os.environ["A5S_PASSWORD"], "credentialId": ""}).encode()),
        timeout=30)
    raise SystemExit("Keycloak didn't send Ana back to the approval page.")
except HTTPError as went:
    location = went.headers["Location"]
assert location.startswith(back), location
token = call(f"{CORE}/approve/token", {"grant_type": "authorization_code", "code_verifier": verifier,
                                       "code": parse_qs(urlsplit(location).query)["code"][0],
                                       "redirect_uri": back})["id_token"]
seen = call(f"{CORE}/approve/settings/{version}/review", {"salt": salt}, token)
assert [c["text"] for c in seen["changes"]] == ["assistant-finance serves Chen Wei as well."], seen
print(call(f"{CORE}/approve/settings/{version}", {"salt": salt}, token))
PY
compose exec -T gateway python - <<'PY'
import os, time, psycopg
for _ in range(60):  # the scheduler asks the core to apply approved settings every minute
    with psycopg.connect(os.environ["A5S_DATABASE_URL"]) as conn:
        serves = conn.execute("select serves from instances where id = 'assistant-finance'").fetchone()[0]
    if "chen" in serves:
        break
    time.sleep(2)
assert "chen" in serves, serves
print("Ana approved the new settings on the core's page, signed in afresh at Keycloak, and the core "
      "applied them.")
PY

compose exec -T gateway a5s ledger tail -n 200 | grep -q '"identity": "verified"'
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

if [ "$keep" = 1 ]; then
  trap - EXIT
  rm -f "$reply"
  cat <<EOF

The stack is still running, to try. Sign in as ana, ben or chen, with the password
A5S_IDP_PASSWORD in $env_file:
  the web chat: http://127.0.0.1:8703/chat/
  Matrix:       http://127.0.0.1:8008, in a Matrix app such as Element, as @ana:a5s.test, say.
                Start a chat with @a5s-assistant:a5s.test, with encryption off.
To stop it: docker compose -p a5s-smoke down -v; rm -rf $env_file $work
EOF
fi
