#!/usr/bin/env bash
# Run a test's dry run (tests/<name>/dryrun_test.py) inside the official Locust image
# (macOS / Linux; Windows: tools/dryrun.ps1).
# The dry run talks only to a fake server on 127.0.0.1 inside the container: nothing reaches sandbox.
#
#   ./tools/dryrun.sh stl-presign-upload
#   VERSION=2.47.0 ./tools/dryrun.sh stl-presign-upload        same Locust version as the VM
#   ./tools/dryrun.sh stl-presign-upload stop hang             only some scenarios
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <test-name> [scenario ...]" >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_name="$1"; shift
version="${VERSION:-latest}"
test_dir="$repo_dir/tests/$test_name"

if [ ! -f "$test_dir/dryrun_test.py" ]; then
  echo "No dryrun_test.py in tests/$test_name" >&2
  exit 1
fi

# Git Bash on Windows: keep paths as they are and give Docker a Windows path
export MSYS_NO_PATHCONV=1
mount_dir="$test_dir"
if pwd -W >/dev/null 2>&1; then mount_dir="$(cd "$test_dir" && pwd -W)"; fi

# --network none: the container has no network access except its own 127.0.0.1
docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -v "$mount_dir:/mnt/locust" \
  --entrypoint python "locustio/locust:$version" /mnt/locust/dryrun_test.py "$@"
