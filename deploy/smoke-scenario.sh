#!/bin/sh
# Runs one of the scenarios a5s ships, besides the sample, on a5s's containers, from the
# same image, with stand-ins for the model, a Matrix homeserver and locked storage. It
# checks that the core runs only a release the scenario's own people approved, signed with
# their made-up keys; that one of its people asks its assistant in Matrix and gets an answer
# from the scenario's records; that the core recorded the homeserver vouching for them; that
# the core works the scenario's obligations out from its records, each naming someone in its
# directory; that its assurance reads who holds each role in the audit trail; and that the
# ledger verifies against its locked copies. deploy/smoke.sh checks the rest with the sample.
# Needs the image first: docker build -t a5s:dev .
#   sh deploy/smoke-scenario.sh master-data       (or software-delivery, or service-desk)
set -eu
cd "$(dirname "$0")/.."
folder=${1:-}
# Each scenario: its class; who signs its first release: its release approver, assurance, an
# engineer of the team that runs a5s and its agents' owner; who asks its assistant, and
# what; and a record the answer must name.
case "$folder" in
  master-data)
    class=a5s.master_data:MasterDataScenario signers="rhea ken tao ines" assurance=ken
    asker=ada agent=mdg-assistant expected=CR0000102
    question="Which change requests are about a bank account?" ;;
  software-delivery)
    class=a5s.software_delivery:SoftwareDeliveryScenario signers="rue ash ugo pam" assurance=ash
    asker=raj agent=dev-assistant expected=DEV-101
    question="Which issues mention checkout?" ;;
  service-desk)
    class=a5s.service_desk:ServiceDeskScenario signers="ren zia max dev" assurance=zia
    asker=sam agent=desk-assistant expected=INC0000001
    question="Which tickets are about the VPN?" ;;
  *) echo "Which scenario? master-data, software-delivery or service-desk"; exit 2 ;;
esac
if command -v cygpath >/dev/null 2>&1; then
  export MSYS2_ARG_CONV_EXCL="${MSYS2_ARG_CONV_EXCL:+$MSYS2_ARG_CONV_EXCL;}/work;/keys;/config"
fi
if ! python3 -c '' >/dev/null 2>&1; then
  python3() { uv run python "$@"; }
fi

env_file=$(mktemp)
reply=$(mktemp)
work=$(mktemp -d)
host_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
chmod a+rx "$work"  # for the containers that sign and record the release
random() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9'; }
password=$(random)
printf 'A5S_DB_PASSWORD=%s\nA5S_SERVICE_TOKEN=%s\nA5S_SEAL_KEYS=%s\n' \
  "$(random)" "$(random)" "$(random)" > "$env_file"
for part in GATEWAY CHANNELS SCHEDULER ANCHOR; do
  echo "A5S_DB_${part}_PASSWORD=$(random)" >> "$env_file"
done
printf 'A5S_ANCHOR_STORE=s3://a5s-ledger/%s\n' "$folder" >> "$env_file"
printf 'A5S_SCENARIO=%s\nA5S_SCENARIO_DIR=/app/scenarios/%s\nA5S_AGENTS_DIR=/app/scenarios/%s/agents\n' \
  "$class" "$folder" "$folder" >> "$env_file"
first=$(ls "scenarios/$folder/agents" | sed -n 1p)  # its first two agents, in pools of
second=$(ls "scenarios/$folder/agents" | sed -n 2p)  # their own
printf 'A5S_POOL_ASSISTANT=%s\n' "$first" >> "$env_file"
if [ -n "$second" ]; then printf 'A5S_POOL_WATCHER=%s\n' "$second" >> "$env_file"; fi
python3 deploy/matrix/configure.py "$work/matrix" >> "$env_file"
compose() { docker compose -p "a5s-$folder" --env-file "$env_file" -f deploy/compose.yaml \
              -f deploy/compose.stub.yaml -f deploy/compose.storage.yaml \
              -f deploy/compose.matrix.yaml "$@"; }
trap 'compose down -v >/dev/null 2>&1; rm -rf "$env_file" "$reply" "$work"' EXIT

compose up -d

# The core runs only a release this deployment's people approved: here, the scenario's own,
# whose made-up keys are in the repository. A real deployment's sign with keys only they hold.
if compose exec -T gateway a5s release status > "$reply" 2>&1; then
  echo "The core would run a release nobody here approved."; exit 1
fi
grep -q "nobody here has approved it yet" "$reply"
compose exec -T gateway a5s release show > "$work/release.yaml"
grep -q "^  $agent:" "$work/release.yaml" || { echo "The release doesn't hold the $agent."; exit 1; }
for person in $signers; do
  docker run --rm --user "$(id -u):$(id -g)" -v "$(host_path "$PWD/scenarios/$folder/keys"):/keys:ro" \
    -v "$(host_path "$work"):/work" -w /work "${A5S_IMAGE:-a5s:dev}" release sign --as "$person" --key "/keys/$person.key"
done
compose run --rm -T -v "$(host_path "$work"):/work" -w /work setup release approve > /dev/null
compose exec -T gateway a5s release status | tail -1
echo "The core waited for the $folder release to be approved by its own people."

# One of the scenario's people asks its assistant, in a direct chat in Matrix
compose exec -T synapse register_new_matrix_user -c /config/homeserver.yaml -u "$asker" \
  -p "$password" --no-admin http://localhost:8008 > /dev/null
A5S_PASSWORD="$password" A5S_ASKER="$asker" A5S_AGENT="$agent" A5S_QUESTION="$question" \
  A5S_EXPECTED="$expected" python3 - <<'PY'
import json, os, time, uuid
from urllib.parse import quote
from urllib.request import Request, urlopen

HOMESERVER = "http://127.0.0.1:8008/_matrix/client/v3"
BOT, ASKER = f"@a5s-{os.environ['A5S_AGENT']}:a5s.test", os.environ["A5S_ASKER"]

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

token = call("POST", "/login", {"type": "m.login.password", "password": os.environ["A5S_PASSWORD"],
                                 "identifier": {"type": "m.id.user", "user": ASKER}})["access_token"]
room = call("POST", "/createRoom", {"is_direct": True, "invite": [BOT], "preset": "trusted_private_chat"},
            token)["room_id"]
at = f"/rooms/{quote(room, safe='')}"
until(f"the {BOT} joining {ASKER}'s chat",
      lambda: BOT in call("GET", f"{at}/joined_members", token=token)["joined"])
call("PUT", f"{at}/send/m.room.message/{uuid.uuid4().hex}",
     {"msgtype": "m.text", "body": os.environ["A5S_QUESTION"]}, token)
said = until(f"the {BOT} answering", lambda: [
    e["content"]["body"] for e in call("GET", f"{at}/messages?dir=b&limit=20", token=token)["chunk"]
    if e["sender"] == BOT and e["type"] == "m.room.message"])
print(f"{ASKER} asked in Matrix: {os.environ['A5S_QUESTION']}\nReply: {said[0]}")
assert os.environ["A5S_EXPECTED"] in said[0], said
PY
compose exec -T gateway a5s ledger tail -n 200 | grep -q '"identity": "verified by matrix"'
echo "The homeserver vouched for $asker in Matrix, and the core recorded it."

compose exec -T gateway python - "$agent" <<'PY'
import sys, time
import psycopg
from a5s import build
from a5s.config import Config

cfg = Config.from_env()
scenario = build.scenario(cfg)
with psycopg.connect(cfg.database_url) as conn:
    running = conn.execute("select id, definition, status from instances order by id").fetchall()
assert running and all(status == "active" for _, _, status in running), running
assert sys.argv[1] in {definition for _, definition, _ in running}, running
print("At work, in the release its people approved:", ", ".join(i for i, _, _ in running))
for _ in range(60):  # the scheduler asks the core what's due every minute
    with psycopg.connect(cfg.database_url) as conn:
        owed = conn.execute("select record, person from obligations where done_at is null "
                            "order by record").fetchall()
    if owed:
        break
    time.sleep(2)
assert owed, "the core worked out no obligations from the scenario's records"
strangers = [person for _, person in owed if scenario.person(person) is None]
assert not strangers, strangers
print(f"The core worked {len(owed)} obligations out from the records, each naming someone in "
      f"the directory, such as {owed[0][0]} for {owed[0][1]}.")
PY

compose exec -T gateway a5s audit report --by "$assurance" > "$work/report"
grep -q "release-approver: ${signers%% *}" "$work/report"
grep -q "approved a release" "$work/report"
echo "Assurance read who holds each role, and who approved the release, in the audit trail."

compose exec -T anchor a5s anchor
compose exec -T anchor a5s ledger verify
echo "Smoke test of the $folder scenario passed."
