#!/usr/bin/env bash
# Build a TSV of (module<TAB>fqcn) for every *Test.kt file in TPipe + its subprojects.
# Used to drive run-list.sh for an upgrade triage sweep.
#
# Output:
#   .hermes/test-results/per-class-sweep/all-test-classes.tsv
#   .hermes/test-results/per-class-sweep/{ROOT,TPipe-Bedrock,TPipe-Defaults,...}.tsv
#
# Filtering:
#   - Skips files containing 'Live' in the basename (live tests need a different gate)
#   - Skips non-test files (heuristic: must contain @Test or @kotlin.test.Test annotation)
#   - Skips fixture helpers, explorers, credential utilities, validation scripts
#
# Module-detection:
#   - Bare class names (no `package` line) at TPipe-Bedrock/src/test/kotlin/* are default-package
#     tests — Gradle's --tests filter takes just the class name (e.g. `ComprehensiveBuilderTest`)
#   - All root-project tests declare `package com.TTT` (verified: P2PHostedRegistryHttpRouteTest.kt
#     begins with `package com.TTT`, TruncateAsStringTest.kt ditto)
#   - Default-package tests at the root don't exist — every root *Test.kt has a package line
set -u
OUT_DIR="${SESSION_DIR:-.hermes/test-results/per-class-sweep}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/all-test-classes.tsv"
: > "$OUT"

scan_module() {
  local mod="$1" root="$2"
  [ -d "$root" ] || return 0
  while IFS= read -r f; do
    base=$(basename "$f" .kt)
    case "$base" in
      *Live*) continue ;;
      *Fixture*|*Helper*|*Explorer|*CredentialUtils|*StreamingFactory|*ValidationScript) continue ;;
    esac
    if ! grep -qE '@Test|@kotlin\.test\.Test' "$f" 2>/dev/null; then
      continue
    fi
    pkg=$(awk '/^package /{print $2; exit}' "$f")
    pkg="${pkg%;}"
    if [ -z "$pkg" ]; then
      fqcn="$base"  # default package
    else
      fqcn="${pkg}.$base"
    fi
    echo -e "${mod}\t${fqcn}" >> "$OUT"
  done < <(find "$root" -name '*Test.kt' -type f 2>/dev/null)
}

scan_module "ROOT"                "src/test/kotlin"
scan_module "TPipe-Bedrock"       "TPipe-Bedrock/src/test/kotlin"
scan_module "TPipe-Defaults"      "TPipe-Defaults/src/test/kotlin"
scan_module "TPipe-GenericOpenAI" "TPipe-GenericOpenAI/src/test/kotlin"
scan_module "TPipe-MCP"           "TPipe-MCP/src/test/kotlin"
scan_module "TPipe-Ollama"        "TPipe-Ollama/src/test/kotlin"
scan_module "TPipe-OpenRouter"    "TPipe-OpenRouter/src/test/kotlin"
scan_module "TPipe-TraceServer"   "TPipe-TraceServer/src/test/kotlin"
scan_module "TPipe-Tuner"         "TPipe-Tuner/src/test/kotlin"

wc -l "$OUT"

# Per-module split into gradle-ready rows (":module:test\tfqcn")
for mod in ROOT TPipe-Bedrock TPipe-Defaults TPipe-GenericOpenAI TPipe-MCP TPipe-Ollama TPipe-OpenRouter TPipe-TraceServer TPipe-Tuner; do
  if [ "$mod" = "ROOT" ]; then GR=":test"; else GR=":${mod}:test"; fi
  awk -F'\t' -v g="$GR" -v m="$mod" '$1==m{printf "%s\t%s\n", g, $2}' "$OUT" > "$OUT_DIR/${mod}.tsv"
done

echo "Done. Per-module TSVs in: $OUT_DIR/"
ls -1 "$OUT_DIR"/*.tsv