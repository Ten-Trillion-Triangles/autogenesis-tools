#!/bin/bash
# Ad-hoc verification script template for PumpStation defect fixes.
#
# Pattern derived from /tmp/hermes-verify-t1-defect8.sh (8/8 PASS) and
# /tmp/hermes-verify-t2-defect10.sh (10/10 PASS) — both produced verified TDD
# evidence in <60s without running `./gradlew test`.
#
# Usage: Copy this file to /tmp/hermes-verify-t<N>-defect<M>.sh, replace the
# TAGS with the defect-specific identifiers, and run.
#
# Exit code: 0 on all PASS, 1 on any FAIL.

set -uo pipefail

cd /home/cage/Desktop/Workspaces/TPipe/TPipe

PASS=0
FAIL=0

report() {
    local label="$1" result="$2" detail="$3"
    if [ "$result" = "PASS" ]; then
        printf "  [PASS] %s\n" "$label"
        PASS=$((PASS + 1))
    else
        printf "  [FAIL] %s — %s\n" "$label" "$detail"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== T<N> ad-hoc verification (Defect <M>) ==="
echo

# TODO: replace with defect-specific Check 1
echo "--- Check 1: <check name> ---"
if <condition>; then
    report "<check-1-name>" "PASS" ""
else
    report "<check-1-name>" "FAIL" "<details>"
fi

# TODO: replace with defect-specific Check 2 — verify the source patch is
# at the expected line range, with a grep on a unique token from your patch.
echo
echo "--- Check 2: source patch in <File>.kt ---"
if grep -q "<unique_token_from_your_patch>" src/main/kotlin/Pipeline/<File>.kt; then
    report "source-edit-presence" "PASS" ""
    PATCH_LINE=$(grep -n "<unique_token_from_your_patch>" src/main/kotlin/Pipeline/<File>.kt | head -1 | cut -d: -f1)
    echo "    line: $PATCH_LINE"
else
    report "source-edit-presence" "FAIL" "patch not found in <File>.kt"
fi

# Check 3 (template): previous-task patches intact (regression guard)
# Add one of these per prior task that should still be present.
echo
echo "--- Check 3: prior-task patches intact ---"
if grep -q "agent.setParentInterface(this)" src/main/kotlin/Pipeline/PumpStationLoop.kt; then
    report "t1-patch-intact" "PASS" ""
else
    report "t1-patch-intact" "FAIL" "T1's setParentInterface patch missing"
fi
# Add similar for T2 (buildPathSchemaFallbackMessage), T3 (invokePath order), etc.

# Check 4 (template): test file compiles in isolation
echo
echo "--- Check 4: test file compiles in isolation ---"
TEST_CP="build/classes/kotlin/main-recompile:build/classes/kotlin/main:build/classes/kotlin/test"
for j in $(find ~/.gradle/caches/modules-2/files-2.1 -name "*.jar" 2>/dev/null \
    | grep -E "(kotlin-stdlib-2\.2\.20\.jar|kotlinx-coroutines-core-jvm|kotlinx-serialization-|junit-jupiter-api|junit-jupiter-engine|junit-platform|opentest4j|apiguardian-api|kotlin-test|kotlin-test-junit|junit-4|slf4j-api|aws-core|aws-json-protocol|httpclient|httpcore|commons-logging|commons-codec|reactivestreams|jsr305|jackson|ktor-)" \
    | grep -v "sources\|javadoc" | sort -u); do
    TEST_CP="$TEST_CP:$j"
done
TEST_CP="$TEST_CP:/home/cage/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-reflect/2.2.20/665c83286bdf6e8ed541ff485e0d322ffeca8d2b/kotlin-reflect-2.2.20.jar"

if /home/linuxbrew/.linuxbrew/bin/kotlinc -cp "$TEST_CP" -d /tmp/_t<n>_compile \
    src/test/kotlin/Pipeline/<TestName>.kt 2>&1 \
    | grep -qE "^.*error:"; then
    COMPILE_ERR=$(/home/linuxbrew/.linuxbrew/bin/kotlinc -cp "$TEST_CP" -d /tmp/_t<n>_compile \
        src/test/kotlin/Pipeline/<TestName>.kt 2>&1 | grep -E "error:" | head -2)
    report "test-compiles-in-isolation" "FAIL" "$(echo "$COMPILE_ERR" | head -1)"
else
    report "test-compiles-in-isolation" "PASS" ""
fi
rm -rf /tmp/_t<n>_compile 2>/dev/null || true

# Check 5 (template): bytecode of patched <File> shows the patch
# Adapt the awk extraction pattern to your patched method name.
echo
echo "--- Check 5: bytecode of patched <File> shows the patch ---"
if [ -d build/classes/kotlin/main-recompile/com/TTT/Pipeline ]; then
    BYTECODE=$(javap -p -c -classpath build/classes/kotlin/main-recompile com.TTT.Pipeline.<KtFile> 2>&1)
    if echo "$BYTECODE" | awk '/public static final.*<YourPatchedMethod>/,/^$/{ print }' | grep -q "<key_new_symbol>"; then
        report "patched-bytecode-shows-<key>" "PASS" ""
    else
        report "patched-bytecode-shows-<key>" "FAIL" "<key_new_symbol> not in compiled <YourPatchedMethod>"
    fi
else
    report "patched-bytecode-shows-<key>" "FAIL" "main-recompile directory missing"
fi

# Check 6 (template): test uses JUnit 5
echo
echo "--- Check 6: test uses JUnit 5 ---"
if grep -q "import org.junit.jupiter.api.Test" src/test/kotlin/Pipeline/<TestName>.kt; then
    report "test-uses-junit5" "PASS" ""
else
    report "test-uses-junit5" "FAIL" "test imports org.junit.Test (JUnit 4) instead of org.junit.jupiter.api.Test"
fi

# Check 7 (template): test has assertions
echo
echo "--- Check 7: test has assertions ---"
if grep -q "assertTrue\|assertEquals\|assertNotNull" src/test/kotlin/Pipeline/<TestName>.kt && \
   grep -q "@Test" src/test/kotlin/Pipeline/<TestName>.kt; then
    assert_count=$(grep -c "@Test" src/test/kotlin/Pipeline/<TestName>.kt)
    report "test-has-assertions" "PASS" "$assert_count test methods"
else
    report "test-has-assertions" "FAIL" "no assertion or @Test annotation"
fi

# Check 8 (template): working tree state
echo
echo "--- Check 8: working tree state ---"
TREE=$(git status --short | wc -l)
echo "    $TREE modified/new files:"
git status --short | sed 's/^/    /'

# Expected: at minimum 1 production file modified + 1 test file added.
# Allow up to 4 (production + 2 tests + 1 support file) without raising scope-creep alarm.
if [ "$TREE" -le 4 ]; then
    report "working-tree-bounded" "PASS" "expected: <File>.kt modified + <TestName>.kt + optional support"
else
    report "working-tree-bounded" "FAIL" "$TREE files modified — possible scope creep"
fi

# Check 9 (template): run the test through the sandbox recipe
echo
echo "--- Check 9: sandbox recipe run ---"
if [ -x /tmp/pumpstation_run_test.sh ]; then
    TEST_CLASS=com.TTT.Pipeline.<TestName> bash /tmp/pumpstation_run_test.sh 2>&1 | tail -3
    EXIT=$?
    if [ $EXIT -eq 0 ]; then
        report "sandbox-recipe-green" "PASS" ""
    else
        report "sandbox-recipe-green" "FAIL" "test runner exit=$EXIT"
    fi
else
    report "sandbox-recipe-green" "FAIL" "/tmp/pumpstation_run_test.sh not present"
fi

# Check 10 (template): no scope creep on the other 12 defects
echo
echo "--- Check 10: no scope creep beyond this defect ---"
EXPECTED_FILES="<File>.kt|<TestName>.kt|com/TTT/testing/"
OTHER_DIRTY=$(git status --short src/ | grep -v "$EXPECTED_FILES" | wc -l)
if [ "$OTHER_DIRTY" -eq 0 ]; then
    report "no-scope-creep" "PASS" ""
else
    report "no-scope-creep" "FAIL" "$OTHER_DIRTY other files modified"
    git status --short src/ | grep -v "$EXPECTED_FILES" | sed 's/^/    /'
fi

echo
echo "=== Summary ==="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo
echo "NOT a suite-green verdict. To get full green, run:"
echo "  ./gradlew :test --tests \"com.TTT.Pipeline.<TestName>\""
echo "(requires Gradle daemon healthy — sandbox cgroup may kill it, see"
echo " references/sandbox-test-recipe.md and gradle-plan-author-pitfalls.md Pitfalls 6+7.)"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
