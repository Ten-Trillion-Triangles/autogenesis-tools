#!/bin/bash
# Hedge phrase audit for competitor comparison pages.
# Verifies the voice-rewrite rules have been applied across all comparison files.
# Returns 0 if clean, 1 if any hedge phrases remain.
#
# Usage: ./scripts/hedge-phrase-audit.sh [path/to/comparison-dir]
# Default: audits both src/pages/comparison/ and src/components/comparison/ComparisonTable.astro
#          (the homepage table uses the same voice/accuracy rules as the dedicated pages)

set -e

# Blacklist phrases. Keep in sync with the SKILL.md blacklist section.
# New phrases get added here as the voice rules evolve.
PHRASES=(
  "honest assessment"
  "reasonable choice"
  "excellent for what it is"
  "well-suited"
  "well-architected"
  "vibrant community"
  "extensive documentation"
  "architectural ceiling"
  "rapid prototyping is the priority"
  "if it fits your"
  "if you have a fixed number of states"
  "you wouldn't switch for familiarity"
  "Not a feature gap. An architectural ceiling"
  "stay with LangGraph"
  "if you're not hitting"
  "announced 2024"
)

# Build the list of targets to scan.
TARGETS=()

if [ -n "$1" ]; then
  # Explicit path provided — use just that
  TARGETS=("$1")
else
  # Default: scan both the comparison page directory and the homepage component
  [ -d "src/pages/comparison" ] && TARGETS+=("src/pages/comparison")
  [ -f "src/components/comparison/ComparisonTable.astro" ] && TARGETS+=("src/components/comparison/ComparisonTable.astro")
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "❌ No comparison files found. Pass an explicit path or run from ttt-site root."
  exit 2
fi

FOUND=0
for phrase in "${PHRASES[@]}"; do
  for target in "${TARGETS[@]}"; do
    if [ -d "$target" ]; then
      hits=$(grep -ril "$phrase" "$target" 2>/dev/null || true)
    elif [ -f "$target" ]; then
      hits=$(grep -il "$phrase" "$target" 2>/dev/null || true)
    else
      continue
    fi
    if [ -n "$hits" ]; then
      echo "❌ '$phrase' found in:"
      for file in $hits; do
        echo "    $file"
      done
      FOUND=$((FOUND+1))
    fi
  done
done

echo ""
if [ "$FOUND" -eq 0 ]; then
  echo "✅ All comparison files clean of hedge phrases."
  exit 0
else
  echo "❌ $FOUND hedge phrase(s) found. Fix before merge."
  exit 1
fi
