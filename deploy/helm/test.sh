#!/bin/sh
# Installs a5s's chart on a Kubernetes cluster of its own, k3s in Docker, which enforces network
# policies, with Postgres beside it, and checks that: the setup job runs before the parts
# start; the core runs no release its people haven't approved, and runs it once a job records
# their signatures; the scheduler reaches the gateway; and the worker reaches the gateway
# alone, never the database, the channels or the internet.
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
docker save "$IMAGE" | docker exec -i "$CLUSTER" ctr -n k8s.io images import - > /dev/null
echo "A cluster of its own is up, with the image in it."

# Postgres, as the deployment's own would be, and the Secret each part reads its own keys of
k create namespace a5s > /dev/null
admin=$(random)
k -n a5s apply -f - > /dev/null <<YAML
apiVersion: v1
kind: Pod
metadata: {name: postgres, labels: {app: postgres}}
spec:
  containers:
    - name: postgres
      image: $POSTGRES
      env:
        - {name: POSTGRES_USER, value: a5s}
        - {name: POSTGRES_PASSWORD, value: "$admin"}
      ports: [{containerPort: 5432}]
      readinessProbe: {exec: {command: [pg_isready, -U, a5s]}, periodSeconds: 2}
---
apiVersion: v1
kind: Service
metadata: {name: postgres}
spec: {selector: {app: postgres}, ports: [{port: 5432}]}
YAML
k -n a5s wait --for=condition=Ready pod/postgres --timeout=300s > /dev/null
set -- --from-literal=database-admin-url="postgresql://a5s:$admin@postgres:5432/postgres"
for part in gateway channels scheduler anchor; do
  password=$(random)
  set -- "$@" --from-literal="database-$part-url=postgresql://a5s_$part:$password@postgres:5432/postgres" \
    --from-literal="database-$part-password=$password"
done
k -n a5s create secret generic a5s "$@" --from-literal=service-token="$(random)" \
  --from-literal=seal-keys="$(random)" > /dev/null

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

reach() {
  k -n a5s exec deploy/a5s-worker -- python -c \
    "import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 5)" "$1" "$2" \
    > /dev/null 2>&1
}
reach a5s-gateway 8700 || { echo "The worker can't reach the gateway."; exit 1; }
for target in "postgres 5432" "a5s-channels 8703" "1.1.1.1 443"; do
  # shellcheck disable=SC2086 # each is a host and a port
  if reach $target; then
    echo "The worker reached $target, which its network policy should stop."
    exit 1
  fi
done
echo "The worker reaches the gateway alone: not the database, the channels or the internet."
echo "Kubernetes test passed."
