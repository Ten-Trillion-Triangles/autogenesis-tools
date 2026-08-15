#!/usr/bin/env bash
# Run a list of (module<TAB>fqcn) pairs sequentially via run-class.sh.
# Source of truth for per-class progress during a TPipe upgrade triage sweep.
#
# Usage:
#   ./run-list.sh <tsv-list> <label>
# Examples:
#   ./run-list.sh .hermes/test-results/2026-07-27-kotlin-231/ROOT.tsv "ROOT"
#
# TSV format (one row per class):
#   :test\tcom.TTT.Pipeline.JunctionTest
#   :TPipe-Bedrock:test\tbedrockPipe.ConstructPipeTest
#   :TPipe-Bedrock:test\tComprehensiveBuilderTest     # default-package — FQCN is just the class name
#
# Build the TSV by parsing package declarations:
#   for f in $(find src/test -name '*Test.kt'); do
#     pkg=$(awk '/^package /{print $2; exit}' "$f" | sed 's/;$//')
#     cls=$(basename "$f" .kt)
#     [ -z "$pkg" ] && fqcn="$cls" || fqcn="${pkg}.${cls}"
#     printf ":test\t%s\n" "$fqcn"
#   done
set -u
LIST="$1"
LABEL="$2"
SESSION_DIR="${SESSION_DIR:-.hermes/test-results/per-class-sweep}"
mkdir -p "$SESSION_DIR"
LOG="$SESSION_DIR/per-class.log"
TOTAL=$(wc -l < "$LIST")
IDX=0
date "+%Y-%m-%d %H:%M:%S $LABEL LOOP START ($TOTAL classes)" >> "$LOG"
while IFS=$'\t' read -r MOD FQCN; do
  [ -z "$MOD" ] || [ -z "$FQCN" ] && continue
  IDX=$((IDX + 1))
  echo "--- $IDX/$TOTAL : $FQCN ($MOD) ---" >> "$LOG"
  "$(dirname "$0")/run-class.sh" "$MOD" "$FQCN"
done < "$LIST"
date "+%Y-%m-%d %H:%M:%S $LABEL LOOP END ($IDX classes done)" >> "$LOG"
echo "=== $LABEL LOOP DONE ===" >> "$LOG"