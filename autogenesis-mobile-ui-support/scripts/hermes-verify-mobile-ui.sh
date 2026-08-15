#!/usr/bin/env bash
# scripts/hermes-verify-mobile-ui.sh
#
# Ad-hoc verification for Autogenesis mobile UI CSS fixes.
# Run after editing night-mode.css to confirm:
#   1. Source CSS contains the new selectors
#   2. Desktop-layout safety: 0 top-level CSS property additions
#   3. Built CSS at processedResources + dist contains the selectors
#   4. Both probe files pass `node --check` syntax validation
#   5. mainmenu probe has LoadingScreen CTA click + no bare window.innerWidth
#   6. Commit lands on Autogenesis-Mobile
#
# NOT a substitute for full suite green. The mobile probes (mainmenu +
# diagnose) require a running dev server with a fresh build to actually
# execute browser tests. This script verifies the static claims.
#
# Usage: bash scripts/hermes-verify-mobile-ui.sh
#        (or copy to /tmp/hermes-verify-*.sh and run there)
#
# Exit 0 = all checks passed; exit 1 = at least one FAIL.

set -uo pipefail

WORKSPACE=/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
PROBES=$WORKSPACE/kvisionApp-e2e

# Set COMMIT to the commit hash you want to verify. Default: HEAD.
COMMIT="${COMMIT:-HEAD}"

echo "=== hermes-verify-mobile-ui.sh (ad-hoc, NOT suite green) ==="
echo "    Verifying commit: $COMMIT"
echo ""

PASS=0
FAIL=0

# ---------- 1. Source CSS contains the mobile fix selectors ----------
echo "1. Source CSS — checking mobile fix selectors are present"

cd "$WORKSPACE"

declare -a CHECKS=(
  "main-menu-bottom > div:has(.btn-play)"   # MainMenu inner hPanel collapse
  "background-size: contain"                # MainMenu wordmark fit
  "billing-modal-window-host .modal-dialog" # Billing modal width
  "billing-modal-title"                     # Billing modal title font-size
  "btn-close-collection"                    # CollectionOverlay corner X
  "collection-tab-button::after"            # CollectionOverlay text label
  "login-widget-window"                     # SettingsWidget positioning
  "shop-credit-card"                        # ShopOverlay GO MONTHLY stack
  "commander-creation-dialog input"         # CommanderCreation input width
  "text-overflow: ellipsis"                 # CommanderCreation ellipsis
)

for sel in "${CHECKS[@]}"; do
  count=$(grep -c "$sel" kvisionApp/src/jsMain/resources/night-mode.css 2>/dev/null || echo 0)
  if [ "$count" -ge 1 ]; then
    echo "   PASS: '$sel' present ($count hits)"
    PASS=$((PASS+1))
  else
    echo "   FAIL: '$sel' MISSING"
    FAIL=$((FAIL+1))
  fi
done

# Desktop-layout safety: every added CSS property line must be indented
# (live inside a @media block). Top-level additions would bleed into desktop.
echo ""
echo "   Desktop-layout safety: every added CSS property is indented (inside @media)"

unindented=$(set +o pipefail; git show "$COMMIT" -- kvisionApp/src/jsMain/resources/night-mode.css \
  | grep -E '^\+[A-Za-z]' \
  | { grep -vE '^\+\+\+' || true; } \
  | { grep -vE '^\+/\*' || true; } \
  | { grep -vE '^\+   ' || true; } \
  | { grep -vE '^\+\*' || true; } \
  | { grep -vE '^\+\s*\*/' || true; } \
  | { grep -vE '^\+\s*$' || true; } \
  | wc -l)
echo "   Top-level (non-indented) additions in commit $COMMIT: $unindented (should be 0)"
if [ "$unindented" -eq 0 ]; then
  echo "   PASS: all CSS property additions are indented (inside @media blocks)"
  PASS=$((PASS+1))
else
  echo "   FAIL: $unindented top-level additions leaked"
  FAIL=$((FAIL+1))
fi

# ---------- 2. Built CSS (processedResources) contains the changes ----------
echo ""
echo "2. Built CSS (processedResources) — webpack emitted the rules"
PROC_CSS="$WORKSPACE/kvisionApp/build/processedResources/js/main/night-mode.css"
if [ -f "$PROC_CSS" ]; then
  proc_size=$(wc -c < "$PROC_CSS")
  echo "   processedResources/night-mode.css exists, size=$proc_size bytes"
  for sel in "main-menu-bottom > div:has" "background-size: contain" "btn-close-collection" "collection-tab-button::after"; do
    c=$(grep -c "$sel" "$PROC_CSS" 2>/dev/null || echo 0)
    if [ "$c" -ge 1 ]; then
      echo "   PASS: '$sel' in built CSS ($c)"
      PASS=$((PASS+1))
    else
      echo "   FAIL: '$sel' missing from built CSS"
      FAIL=$((FAIL+1))
    fi
  done
else
  echo "   FAIL: $PROC_CSS does not exist — run :kvisionApp:jsProcessResources"
  FAIL=$((FAIL+1))
fi

# ---------- 3. Dist CSS — what static-server-8080.mjs actually serves ----------
echo ""
echo "3. Dist CSS — what static server serves to the probes"
DIST_CSS="$WORKSPACE/kvisionApp/build/dist/js/productionExecutable/night-mode.css"
if [ -f "$DIST_CSS" ]; then
  dist_size=$(wc -c < "$DIST_CSS")
  echo "   dist/night-mode.css exists, size=$dist_size bytes"
  for sel in "main-menu-bottom > div:has" "background-size: contain" "btn-close-collection" "collection-tab-button::after"; do
    c=$(grep -c "$sel" "$DIST_CSS" 2>/dev/null || echo 0)
    if [ "$c" -ge 1 ]; then
      echo "   PASS: '$sel' in dist CSS ($c)"
      PASS=$((PASS+1))
    else
      echo "   NOTE: '$sel' not in dist — copy processedResources/night-mode.css over"
    fi
  done
else
  echo "   FAIL: $DIST_CSS does not exist"
  FAIL=$((FAIL+1))
fi

# ---------- 4. Probe files are well-formed ----------
echo ""
echo "4. Probe scripts — Node syntax check"
for probe in "$PROBES/probes/mainmenu-mobile-portrait.mjs" "$PROBES/probes/diagnose-all-mobile.mjs"; do
  if [ -f "$probe" ]; then
    if node --check "$probe" 2>/dev/null; then
      echo "   PASS: $(basename $probe) syntax OK"
      PASS=$((PASS+1))
    else
      echo "   FAIL: $(basename $probe) syntax error"
      node --check "$probe"
      FAIL=$((FAIL+1))
    fi
  else
    echo "   SKIP: $(basename $probe) not found"
  fi
done

# ---------- 5. mainmenu probe is correctly constructed ----------
echo ""
echo "5. mainmenu probe — LoadingScreen CTA click + viewport access inside evaluate"
MAINMENU="$PROBES/probes/mainmenu-mobile-portrait.mjs"
if [ -f "$MAINMENU" ]; then
  if grep -q 'loading-screen-cta' "$MAINMENU"; then
    echo "   PASS: LoadingScreen CTA click step present"
    PASS=$((PASS+1))
  else
    echo "   FAIL: LoadingScreen CTA click step MISSING"
    FAIL=$((FAIL+1))
  fi

  if grep -q 'page.evaluate' "$MAINMENU"; then
    echo "   PASS: uses page.evaluate"
    PASS=$((PASS+1))
  else
    echo "   FAIL: missing page.evaluate"
    FAIL=$((FAIL+1))
  fi

  eval_count=$(grep -c 'page.evaluate' "$MAINMENU" 2>/dev/null || echo 0)
  win_count=$(grep -c 'window.innerWidth' "$MAINMENU" 2>/dev/null || echo 0)
  echo "   page.evaluate opens: $eval_count, window.innerWidth references: $win_count"
  if [ "$win_count" -le "$eval_count" ]; then
    echo "   PASS: window.innerWidth references <= page.evaluate opens"
    PASS=$((PASS+1))
  else
    echo "   FAIL: $win_count window.innerWidth refs but only $eval_count evaluate opens"
    FAIL=$((FAIL+1))
  fi

  # Precise check: no bare window.innerWidth at probe top-level
  awk_result=$(awk '
    /page\.evaluate/ { in_eval++ }
    /\}\)/ && in_eval > 0 { in_eval-- }
    /window\.innerWidth/ {
      if (in_eval <= 0) {
        print "     at line " NR ": " $0
        bare++
      }
    }
    END { exit (bare > 0 ? 1 : 0) }
  ' "$MAINMENU")
  awk_status=$?
  if [ "$awk_status" -eq 0 ]; then
    echo "   PASS: no bare window.innerWidth outside page.evaluate"
    PASS=$((PASS+1))
  else
    echo "   FAIL: bare window.innerWidth reference found outside evaluate"
    echo "$awk_result"
    FAIL=$((FAIL+1))
  fi
else
  echo "   FAIL: $MAINMENU not found"
  FAIL=$((FAIL+1))
fi

# ---------- 6. Commit landed on Autogenesis-Mobile ----------
echo ""
echo "6. Commit landed on Autogenesis-Mobile"

commit_hash=$(git log --oneline Autogenesis-Mobile | head -20 | awk '{print $1}')
found=0
for hash in $commit_hash; do
  if [ "$hash" = "$COMMIT" ]; then
    found=1
    break
  fi
done

if [ "$found" -eq 1 ]; then
  echo "   PASS: commit $COMMIT in Autogenesis-Mobile history"
  PASS=$((PASS+1))
  git log --oneline -1 "$COMMIT"
else
  echo "   FAIL: commit $COMMIT not found in Autogenesis-Mobile history"
  echo "   Recent commits:"
  git log --oneline -5
  FAIL=$((FAIL+1))
fi

# ---------- Summary ----------
echo ""
echo "=== Summary: $PASS PASS / $FAIL FAIL ==="
if [ "$FAIL" -gt 0 ]; then
  echo "Ad-hoc verification FAILED — see FAIL lines above."
  exit 1
fi
echo "Ad-hoc verification PASSED. This is ad-hoc evidence only — not a substitute"
echo "for a full suite re-run. The mobile-render probes require a running dev"
echo "server with a fresh build to execute live browser tests."