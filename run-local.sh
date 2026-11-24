#!/usr/bin/env bash
# Run Locust locally in Docker with one test's locustfile.py (macOS / Linux; Windows: run-local.ps1).
# Then open http://localhost:8089 in the browser.
#
#   ./run-local.sh                                   default test (stl-presign-upload), newest Locust
#   TEST=stl-presign-upload ./run-local.sh           pick a test folder under tests/
#   VERSION=2.47.0 ./run-local.sh                    a specific Locust version (use the one on the VM)
#   DETACH=1 ./run-local.sh                          run in the background; stop: docker stop rata-locust-local
#   ./run-local.sh --class-picker                    extra Locust options go at the end
#
# A local run is for rehearsal only (1 user, small values). Real load tests run on the
# Locust VM in Singapore, because from a laptop the results are limited by your internet.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
test_name="${TEST:-stl-presign-upload}"
version="${VERSION:-latest}"
port="${PORT:-8089}"
test_dir="$repo_dir/tests/$test_name"

if [ ! -f "$test_dir/locustfile.py" ]; then
  echo "No locustfile.py in tests/$test_name" >&2
  exit 1
fi

name="rata-locust-local"
docker rm -f "$name" >/dev/null 2>&1 || true

if [ "${DETACH:-}" = "1" ]; then mode="-d"; else mode="-it"; fi

echo "Test: $test_name"
echo "Locust dashboard: http://localhost:$port"
if [ "$mode" = "-d" ]; then
  echo "Running in the background. Stop it with: docker stop $name"
else
  echo "Press Ctrl+C to stop."
fi

# Git Bash on Windows: keep paths as they are and give Docker a Windows path
export MSYS_NO_PATHCONV=1
mount_dir="$test_dir"
if pwd -W >/dev/null 2>&1; then mount_dir="$(cd "$test_dir" && pwd -W)"; fi

docker run --rm "$mode" --name "$name" -p "$port:8089" -v "$mount_dir:/mnt/locust" \
  "locustio/locust:$version" -f /mnt/locust/locustfile.py "$@"
