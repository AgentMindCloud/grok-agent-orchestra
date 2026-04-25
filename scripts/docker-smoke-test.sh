#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Build the grok-agent-orchestra image, run it, and verify the dashboard
# answers HTTP 200 on /api/health. Prints a non-zero exit on any failure.
#
# Usage:
#   ./scripts/docker-smoke-test.sh                    # builds, runs, tears down
#   IMAGE=ghcr.io/agentmindcloud/grok-agent-orchestra:latest \
#     ./scripts/docker-smoke-test.sh --no-build       # skip build, pull instead
#
# Designed to be safe to run repeatedly and on CI:
#   - exits non-zero if any step fails (set -euo pipefail)
#   - cleans up the test container even on error (trap)
#   - tags the build with a timestamped tag so it doesn't clobber the user's
#     :latest in their local cache.
# -----------------------------------------------------------------------------

set -euo pipefail

IMAGE="${IMAGE:-orchestra-test:smoke-$(date +%s)}"
PORT="${PORT:-18000}"
CONTAINER_NAME="orchestra-smoke-$RANDOM"
BUILD=1

for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

cleanup() {
  if docker ps -aq --filter "name=^${CONTAINER_NAME}$" | grep -q .; then
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

step() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n'  "$*"; }
fail() { printf '\033[1;31m  ✗ %s\033[0m\n'  "$*" >&2; exit 1; }

if [[ "$BUILD" == "1" ]]; then
  step "Build $IMAGE"
  docker build -t "$IMAGE" .
  ok "build succeeded"
fi

step "Verify CLI entry point inside the image"
if docker run --rm "$IMAGE" --version | grep -q "grok-orchestra"; then
  ok "grok-orchestra --version reports a version"
else
  fail "grok-orchestra --version did not respond as expected"
fi

step "Boot the dashboard on host port ${PORT}"
docker run --rm -d \
  -p "${PORT}:8000" \
  --name "$CONTAINER_NAME" \
  "$IMAGE" >/dev/null
ok "container started"

step "Wait for /api/health (≤ 30s)"
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"
for i in $(seq 1 60); do
  if curl --silent --fail "$HEALTH_URL" >/dev/null 2>&1; then
    body="$(curl --silent "$HEALTH_URL")"
    case "$body" in
      *'"status":"ok"'*)
        ok "health endpoint returned $body"
        break
        ;;
    esac
  fi
  sleep 0.5
  if [[ "$i" == "60" ]]; then
    fail "health endpoint did not become ready in 30s"
  fi
done

step "Teardown"
docker stop "$CONTAINER_NAME" >/dev/null
ok "container stopped"

printf '\n\033[1;32mAll smoke checks passed.\033[0m\n'
