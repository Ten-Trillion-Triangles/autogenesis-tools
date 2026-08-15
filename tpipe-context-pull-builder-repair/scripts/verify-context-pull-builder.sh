#!/usr/bin/env bash
# Captures fresh verification evidence for a context-pull-builder repair.
# Usage: ./verify-context-pull-builder.sh <focused-test-class> [adjacent-test-class ...]
#
# Always uses --rerun-tasks so Gradle cannot short-circuit with UP-TO-DATE.

set -euo pipefail

focused="${1:?focused test class required}"
shift

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$repo_root"

# Build the test filter for the rerun.
tests=("--tests" "$focused")
for adjacent in "$@"; do
    tests+=("--tests" "$adjacent")
done

# 1. Rerun the focused test class to defeat the Gradle cache.
./gradlew :test --rerun-tasks "${tests[@]}"

# 2. Diff-check the changed paths. Pass them as args:  -- paths/to/A.kt paths/to/B.kt
#    (this script does not know the changed paths; the caller invokes it directly
#     and chains git diff --check.)