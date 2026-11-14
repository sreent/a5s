#!/bin/sh
# Installs a5s's chart on a Kubernetes cluster of its own, k3s in Docker, which enforces network
# policies, with Postgres beside it, and checks that: the setup job runs before the parts
# start; the core runs no release its people haven't approved, and runs it once a job records
# their signatures; the scheduler reaches the gateway, and never finds it away while it's
# replaced; each worker pool, the shared one and each agent's own, reaches the gateway alone,
# never the database, the channels, another pool or the internet; and the sandbox, a second
# release in a namespace of its own, on a database server of its own, tries a draft the
# studio sends it, is reached by a5s's channels alone, and reaches nothing of a5s's.
# Needs the image first: docker build -t a5s:dev .
set -eu
cd "$(dirname "$0")/../.."

K3S=rancher/k3s:v1.31.4-k3s1@sha256:627fc392e5e7992fb8aa738fb04bc0c9ae9a068999cb4cfbea5858661cd79d04
HELM=alpine/helm:3.16.3@sha256:ed9dfc49d43d034df3f9880eb777caf0183e5156508672478b80412c63f3db4f
POSTGRES=postgres:16@sha256:1beaa3084eee2676f20a9cd9928f0bf2c5bf674f8e49f81017912183d377c61c
IMAGE=${A5S_IMAGE:-a5s:dev}
CLUSTER=a5s-k3s

work=$(mktemp -d)
chmod a+rwx "$work"  # for the containers that sign the release
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then  # what the cluster shows, to see why
    docker exec "$CLUSTER" kubectl -n a5s get pods,jobs 2>&1 || true
    for part in setup approve; do
      docker exec "$CLUSTER" kubectl -n a5s logs "job/a5s-$part" 2>&1 | tail -30 || true
    done
    docker exec "$CLUSTER" kubectl -n a5s logs deploy/a5s-gateway --tail=30 2>&1 || true
    docker exec "$CLUSTER" kubectl -n a5s-sandbox get pods 2>&1 || true
    docker exec "$CLUSTER" kubectl -n a5s-sandbox logs deploy/a5s-sandbox --tail=30 2>&1 || true
  fi
  docker rm -f "$CLUSTER" > /dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

k() { docker exec -i "$CLUSTER" kubectl "$@"; }
helm() { docker run --rm --network host -e KUBECONFIG=/work/kubeconfig -v "$work:/work" \
           -v "$PWD/deploy/helm:/charts:ro" "$HELM" "$@"; }
random() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32; }

docker run -d --name "$CLUSTER" --privileged -p 127.0.0.1:6443:6443 "$K3S" \
  server --disable traefik --disable metrics-server --write-kubeconfig-mode 644 > /dev/null
for _ in $(seq 1 90); do
  k get nodes 2>/dev/null | grep -q " Ready" && break
  sleep 2
done
k wait --for=condition=Ready node --all --timeout=120s > /dev/null
docker exec "$CLUSTER" cat /etc/rancher/k3s/k3s.yaml > "$work/kubeconfig"
chmod 600 "$work/kubeconfig"  # the cluster's own credentials, for its helm alone
docker save "$IMAGE" | docker exec -i "$CLUSTER" ctr -n k8s.io images import - > /dev/null
echo "A cluster of its own is up, with the image in it."

# Postgres, as the deployment's own would be, and the Secret each part reads its own keys of
postgres() {  # a database server, in a namespace, as its administrator's password has it
  k -n "$1" apply -f - > /dev/null <<YAML
apiVersion: v1
kind: Pod
metadata: {name: postgres, labels: {app: postgres}}
spec:
  containers:
    - name: postgres
      image: $POSTGRES
      env:
        - {name: POSTGRES_USER, value: a5s}
        - {name: POSTGRES_PASSWORD, value: "$2"}
      ports: [{containerPort: 5432}]
      readinessProbe: {exec: {command: [pg_isready, -U, a5s]}, periodSeconds: 2}
---
apiVersion: v1
kind: Service
metadata: {name: postgres}
spec: {selector: {app: postgres}, ports: [{port: 5432}]}
YAML
  k -n "$1" wait --for=condition=Ready pod/postgres --timeout=300s > /dev/null
}
k create namespace a5s > /dev/null
admin=$(random)
shared=$(random)  # the token the studio and the sandbox share
postgres a5s "$admin"
set -- --from-literal=database-admin-url="postgresql://a5s:$admin@postgres:5432/postgres"
for part in gateway channels scheduler anchor; do
  password=$(random)
  set -- "$@" --from-literal="database-$part-url=postgresql://a5s_$part:$password@postgres:5432/postgres" \
    --from-literal="database-$part-password=$password"
done
k -n a5s create secret generic a5s "$@" --from-literal=service-token="$(random)" \
  --from-literal=seal-keys="$(random)" --from-literal=sandbox-token="$shared" > /dev/null

helm install a5s /charts/a5s -n a5s -f /charts/ci-values.yaml --wait --timeout 10m > /dev/null
[ "$(k -n a5s get job a5s-setup -o jsonpath='{.status.succeeded}')" = 1 ]
echo "The setup job set up the schema and applied the signed settings, and the parts are up."

# The core runs only a release this deployment's people approved: here the sample's made-up
# people, whose keys are in the repository.
if k -n a5s exec deploy/a5s-gateway -- a5s release status > "$work/reply" 2>&1; then
  echo "The core would run a release nobody here approved."
  exit 1
fi
grep -q "nobody here has approved it yet" "$work/reply"
k -n a5s exec deploy/a5s-gateway -- a5s release show > "$work/release.yaml"
for person in priya tomas rosa kofi; do
  docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/scenarios/sample/keys:/keys:ro" \
    -v "$work:/work" -w /work "$IMAGE" release sign --as "$person" --key "/keys/$person.key" > /dev/null
done
docker cp "$work/release.yaml" "$CLUSTER:/tmp/release.yaml"
docker cp "$work/release.sig" "$CLUSTER:/tmp/release.sig"
k -n a5s create configmap a5s-release --from-file=/tmp/release.yaml --from-file=/tmp/release.sig > /dev/null
helm upgrade a5s /charts/a5s -n a5s --reuse-values --set release.approval=a5s-release \
  --wait --timeout 10m > /dev/null
k -n a5s exec deploy/a5s-gateway -- a5s release status | tail -1 | grep -q "Approved here."
echo "The core waited for the release to be approved here, and a job recorded its approval."

k -n a5s exec deploy/a5s-scheduler -- a5s status | grep -q "a5s over the last day"
echo "The scheduler reaches the gateway."

# As on an upgrade, the core is replaced: its new pod is ready before the old one stops, so
# what the scheduler and the workers send it never finds it away. The scheduler connects to it
# five times a second throughout, and none may fail.
k -n a5s exec deploy/a5s-scheduler -- python -c '
import socket, time
failed, until = 0, time.monotonic() + 90
while time.monotonic() < until:
    try:
        socket.create_connection(("a5s-gateway", 8700), 2).close()
    except OSError:
        failed += 1
    time.sleep(0.2)
print(failed)' > "$work/away" &
watching=$!
sleep 5
k -n a5s rollout restart deployment/a5s-gateway > /dev/null
k -n a5s rollout status deployment/a5s-gateway --timeout=120s > /dev/null
wait "$watching"
if [ "$(cat "$work/away")" != 0 ]; then
  echo "The core was away as it was replaced: $(cat "$work/away") connections to it failed."
  exit 1
fi
echo "The core was never away as it was replaced: its new pod was ready before the old one stopped."

[ "$(k -n a5s get pods -l app.kubernetes.io/component=anchor \
  -o jsonpath='{.items[0].metadata.labels.a5s\.test/workload-identity}')" = on ]
echo "The copier's pods carry the labels a cloud's workload identity needs."

reach_from() {  # from a part's pod, in a namespace: whether it reaches a host and port
  k -n "$1" exec "deploy/$2" -- python -c \
    "import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 5)" "$3" "$4" \
    > /dev/null 2>&1
}
reach() { reach_from a5s "$@"; }
pools="a5s-worker a5s-worker-assistant a5s-worker-watcher"  # the shared, and each agent's
for pool in $pools; do
  reach "$pool" a5s-gateway 8700 || { echo "$pool can't reach the gateway."; exit 1; }
  other=a5s-worker-watcher  # another pool
  [ "$pool" = "$other" ] && other=a5s-worker
  for target in "postgres 5432" "a5s-channels 8703" "$other 8702" "1.1.1.1 443"; do
    # shellcheck disable=SC2086 # each is a host and a port
    if reach "$pool" $target; then
      echo "$pool reached $target, which its network policy should stop."
      exit 1
    fi
  done
  reach a5s-scheduler "$pool" 8702 || { echo "The scheduler can't reach $pool."; exit 1; }
done
echo "Each worker pool reaches the gateway alone: not the database, the channels, another pool"
echo "or the internet. The scheduler reaches each."

# The sandbox: a second release of the chart, in a namespace of its own, on a database server
# of its own, which a5s's channels, set up for it by ci-values.yaml, send a draft to try
k create namespace a5s-sandbox > /dev/null
own=$(random)
postgres a5s-sandbox "$own"
k -n a5s-sandbox create secret generic a5s --from-literal=sandbox-token="$shared" \
  --from-literal=sandbox-database-url="postgresql://a5s:$own@postgres:5432/postgres" > /dev/null
helm install a5s /charts/a5s -n a5s-sandbox -f /charts/ci-values.yaml --set mode=sandbox \
  --wait --timeout 10m > /dev/null
k -n a5s exec deploy/a5s-channels -- python -c '
import os
from pathlib import Path

import httpx

from a5s.core import drafts

url, token = os.environ["A5S_SANDBOX_URL"], os.environ["A5S_SANDBOX_TOKEN"]
said = httpx.post(f"{url}/sandbox/tries", headers={"Authorization": f"Bearer {token}"}, timeout=120,
                  json={"key": "chart1", "files": drafts.folder_files(Path("/app/agents/assistant")),
                        "person": "ana", "text": "Which questions mention an invoice?"})
assert said.status_code == 200, said.text
said = said.json()
assert said["reply"].startswith("(A stand-in model.)"), said["reply"]
assert [c["decision"] for c in said["run"]["calls"]] == ["allow"], said["run"]["calls"]
assert httpx.get(f"{url}/sandbox", timeout=30).status_code == 401  # without the token
' || { echo "The studio couldn't try a draft in the sandbox."; exit 1; }
echo "The sandbox tried a draft a5s's channels sent it, through the core's checks, on its stand-in."
for part in a5s-gateway a5s-scheduler a5s-worker; do
  if reach "$part" a5s-sandbox.a5s-sandbox 8710; then
    echo "$part reached the sandbox, which only the channels should."
    exit 1
  fi
done
reach_from a5s-sandbox a5s-sandbox postgres 5432 || { echo "The sandbox can't reach its database."; exit 1; }
for target in "postgres.a5s 5432" "a5s-gateway.a5s 8700" "a5s-channels.a5s 8703" "1.1.1.1 443"; do
  # shellcheck disable=SC2086 # each is a host and a port
  if reach_from a5s-sandbox a5s-sandbox $target; then
    echo "The sandbox reached $target, which its network policy should stop."
    exit 1
  fi
done
echo "Only the channels reach the sandbox, and it reaches its own database alone: nothing of"
echo "a5s's, nor the internet, with only its stand-in model."
echo "Kubernetes test passed."
