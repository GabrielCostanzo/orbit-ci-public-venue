#!/bin/sh
# Runs on the selected Docker engine, including a remote context. No host port.
set -eu
image=${1:?Pass the immutable image reference}
case "$image" in *@sha256:*) ;; *) echo 'Use an image reference with @sha256:digest' >&2; exit 2;; esac
# Name the owned container before launch: cancellation can lose the run response.
container="buildbarrel-billing-api-smoke-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
trap 'docker rm --force "$container" >/dev/null' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker run --name "$container" --detach --network none --read-only --cap-drop ALL --security-opt no-new-privileges "$image" >/dev/null
attempt=0
while [ "$attempt" -lt 20 ]; do
  if docker exec "$container" python -c 'import json, urllib.request; r=urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2); b=json.load(r); assert r.status == 200 and b == {"application": "billing-api", "healthy": True}' >/dev/null 2>&1; then
    echo 'GET /health -> 200; billing-api is healthy'
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
echo 'billing-api did not pass its health check' >&2
exit 1
