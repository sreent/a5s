#!/bin/sh
# A soak test. Starts the stack as the smoke test does, and checks it the same way, then has
# the sample's people talk to its agents for a while: 30 minutes, unless given another number.
# Ana asks for long tasks too, and half way through, the core, the scheduler and the
# assistant's workers restart. Then it checks that every message had one answer, in time, and
# no message was lost or answered twice; that every task she started ended done, told her once,
# and left no lease; that no part's memory, nor Postgres's connections, kept growing once the
# stack had warmed up; that no part logged an error; and that the ledger verifies against its
# locked copies. Then it prints the measures, with what each run cost. It finds what no test
# that runs for seconds can: leaks, locks that pile up, and work done twice.
# Needs the image first: docker build -t a5s:dev .
set -eu
cd "$(dirname "$0")/.."
minutes=${1:-30}
if ! python3 -c '' >/dev/null 2>&1; then
  python3() { uv run python "$@"; }
fi

env_file=$(mktemp)
work=$(mktemp -d)
compose() { docker compose -p a5s-smoke --env-file "$env_file" -f deploy/compose.yaml \
              -f deploy/compose.stub.yaml -f deploy/compose.identity.yaml \
              -f deploy/compose.storage.yaml -f deploy/compose.matrix.yaml "$@"; }  # as smoke.sh
trap 'compose down -v >/dev/null 2>&1; rm -rf "$env_file" "$work"' EXIT

A5S_SMOKE_ENV="$env_file" A5S_SMOKE_WORK="$work" sh deploy/smoke.sh --keep > "$work/smoke.log" 2>&1 ||
  { cat "$work/smoke.log"; exit 1; }
echo "The smoke test passed, and left the stack running."

started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
A5S_PASSWORD=$(sed -n 's/^A5S_IDP_PASSWORD=//p' "$env_file") \
  python3 deploy/soak.py "$minutes" "${A5S_SOAK_FOUND:-$work/found.json}"

compose exec -T gateway python - <<'PY'
import os, time, psycopg
for _ in range(90):  # what's still being answered, once the people have stopped talking
    with psycopg.connect(os.environ["A5S_DATABASE_URL"]) as conn:
        waiting = conn.execute("select count(*) as n from inbound where answered_at is null"
                               ).fetchone()[0]
    if not waiting:
        break
    time.sleep(2)
assert not waiting, f"{waiting} messages were never answered"
with psycopg.connect(os.environ["A5S_DATABASE_URL"]) as conn:
    twice = conn.execute(
        "select count(*) from (select trigger->>'inbound' from runs where trigger->>'kind' = "
        "'message' group by 1 having count(*) > 1) again").fetchone()[0]
    open_runs = conn.execute("select count(*) from runs where outcome is null "
                             "and opened_at < now() - interval '5 minutes'").fetchone()[0]
    answered = conn.execute("select count(*) from inbound").fetchone()[0]
assert not twice, f"{twice} messages were run more than once"
assert not open_runs, f"{open_runs} runs are still open after five minutes"
print(f"All {answered} messages the core received were answered, each by one run, and "
      "no run was left open.")
PY

if compose logs --no-color --since "$started" gateway channels scheduler worker \
       worker-assistant worker-watcher anchor 2>&1 |
     grep -E "Traceback|ERROR|CRITICAL" > "$work/errors"; then
  head -40 "$work/errors"
  echo "A part logged errors while people were talking to it."; exit 1
fi
echo "No part logged an error while people were talking to it."

compose exec -T anchor a5s anchor > /dev/null
compose exec -T anchor a5s ledger verify
echo "The measures, as the pilot's shadow week reads what a run costs:"
compose exec -T gateway a5s measures --days 1
echo "Soak test passed."
