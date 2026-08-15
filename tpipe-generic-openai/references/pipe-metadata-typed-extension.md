# PipeMetadata as a typed-extension channel for one-off serializer features

When a provider needs a serializer-side feature that is too narrow to
justify a first-class pipe variable (e.g. Bedrock Mantle GPT-5.6 prompt
caching, Anthropic Extended Thinking, OpenAI prompt-cache-key), the
`pipeMetadata` map on the base `Pipe` class is the canonical escape
hatch. This reference captures the 4-step pattern that emerged from the
2026-08-03 Mantle GPT-5.6 explicit-caching work — every future
typed-metadata extension will trip the same wires.

## The four-step pattern

1. **Carrier type + key constant + sanity guard.** Typed metadata
   object (`MantleGpt56PromptCacheMetadata`) + namespaced key
   (`"bedrockMantle.gpt56.promptCaching"`) + a `supports…()` predicate
   that throws on misuse. The throw is deliberate — silently ignoring
   a requested cost-control mechanism makes usage and billing
   impossible to reason about.

2. **Serializer-options widening.** Add a `RequestSerializationOptions`
   data class with a `metadata: Map<String, Any?>` field. Widen the
   `RequestSerializer.serialize(...)` signature to accept it. Use a
   default value so existing 2-arg call sites still compile
   (`options: RequestSerializationOptions = RequestSerializationOptions()`).
   The OpenAI / Anthropic serializers ignore the bag; the targeted
   serializer (e.g. Responses) reads the keys.

3. **Wire-emission + boundary transformation.** Inside the targeted
   serializer, read the carrier from the options bag, validate the
   (model, apiMode) combination, and emit the wire fields. For the
   Mantle case, that included a `developer`-role input-block
   transformation when the boundary mode was `AFTER_INSTRUCTIONS`.

4. **Caller-facing extension.** Provide a `GenericOpenAIPipe.<verb>…`
   extension function that populates the metadata under the agreed
   key. The extension does NOT grow `GenericOpenAIPipe`'s public API
   surface — it just calls `pipeMetadata[key] = carrier`.

## Pitfall 1 — `pipeMetadata` is `MutableMap<Any, Any>`, not `Map<String, Any?>`

The base `Pipe` class declares `val pipeMetadata = mutableMapOf<Any, Any>()`
at `Pipe.kt:1881`. The keys are typed `Any` because the historical
agreement allows string keys (every existing caller uses them) while
leaving the door open for non-string keys if a future feature needs
them. The serializer-options widening exposes a `Map<String, Any?>`
because the serializer only reads string keys in practice.

The cast at the call site looks like this:

```kotlin
val jsonRequest = requestSerializer.serialize(
    request, apiMode,
    @Suppress("UNCHECKED_CAST")
    RequestSerializationOptions(metadata = pipeMetadata as Map<String, Any?>),
)
```

The `@Suppress` is the load-bearing part — without it, the Kotlin
compiler refuses the cast because `MutableMap<Any, Any>` is not
provably `Map<String, Any?>`. The cast is safe because every existing
caller writes string keys (verified via `grep -rn 'pipeMetadata\[' src/main`
across the codebase). New typed-metadata extensions should follow the
same pattern.

## Pitfall 2 — `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` for wire fields whose default Mantle requires

`OpenAIResponsesRequestSerializer` uses `encodeDefaults = false` so
today's wire shape is unchanged when new fields are null. That means
**default-valued fields are stripped from the wire payload** unless
explicitly annotated otherwise. For a metadata carrier field whose
value Mantle requires to be present (e.g. `prompt_cache_breakpoint.mode`
must be `"explicit"` on the wire, not omitted), the rule is:

```kotlin
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class PromptCacheBreakpoint(
    @SerialName("mode")
    @EncodeDefault(EncodeDefault.Mode.ALWAYS)
    val mode: String = "explicit",
)
```

The `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` annotation forces the
field onto the wire even when its value equals the default. Without
this annotation, Mantle receives a `prompt_cache_breakpoint: {}` object
on the wire (or the field is omitted entirely) and may reject the
request. The cost: every fields is now permanently pinned in the wire
schema. If you ever need to send `prompt_cache_breakpoint: { mode:
"implicit" }` in the future, the annotation already supports it — the
`mode` field is always serialized, the value just varies.

The converse — the wire field is optional and the receiver treats absence
as "use default" — does NOT need this annotation. Only apply it when the
receiver requires the field to be present.

**Detection**: if a wire field has a defaulted value AND a serialization
test asserts the field is present on the wire, the test will fail RED
without the annotation. The fix is the annotation, not the test.

## Pitfall 3 — A `RequestSerializer` signature widening breaks the existing `OpenAIRequestSerializer` dispatch passthrough

The `OpenAIRequestSerializer` class is a passthrough that delegates
`ApiMode.OpenAIResponses` mode to the dedicated `OpenAIResponsesRequestSerializer`:
see `api/OpenAIRequestSerializer.kt:18-27`. When widening the base
`RequestSerializer` interface signature, the passthrough MUST also
forward the new options parameter. Easy to miss because the
`OpenAIRequestSerializer` itself does not use the options — it just
forwards them. The compile error you'll see if you forget:

```text
error: 'serialize' is deprecated. ...
```

or:

```text
Argument type mismatch: actual type is 'RequestSerializationOptions',
but 'RequestSerializationOptions' was expected.
```

depending on whether the parent class has a default. With the default
in place, the unset-parameter form works on the interface but the
specific type mismatch still fires on the override.

## Pitfall 4 — Pre-existing baseline test rot blocks `compileTestKotlin` even when your changes are clean

The `TPipe-GenericOpenAI` module has at least 4 pre-existing test
classes that fail to compile against the current `main` branch tip:

- `GenericOpenAIPipeStreamingCallbacksLiveTest.kt:56,106`
- `MiniMaxFeaturesLiveTest.kt:318`
- `OpenAIResponsesLiveTest.kt:116`
- `StreamingInputTokenTracingTest` (3 Anthropic-streaming cases)

All 4 fail identically on a clean `main` HEAD without any of your
changes (verified via `git stash` + `./gradlew
:TPipe-GenericOpenAI:compileTestKotlin` on the unmodified branch).
They are class A pre-existing baseline failures per the pitfall
recipe in `software-development/interactive-plan` (Phase 4 verification
discipline).

The `compileTestKotlin` task compiles ALL test files in the module in
one pass. If ANY test class fails to compile, the whole task fails,
and no test in the module can run. So even a pristine new test
cannot be exercised via `--tests "<NewClass>"` because the compile
fails before the test JVM starts.

**Recipe — stash-and-restore with `trap` on EXIT:**

```bash
#!/bin/bash
# Verification script that runs the test compiler without the broken
# baseline tests, then restores them on exit regardless of pass/fail.
set -u
RESULTS_DIR="/tmp/hermes-verify-<topic>-results-$$"
BASELINE_DIR="/tmp/hermes-verify-<topic>-baseline-broken-$$"
mkdir -p "$RESULTS_DIR" "$BASELINE_DIR"

BASELINE_BROKEN_FILES=(
    "src/test/kotlin/.../GenericOpenAIPipeStreamingCallbacksLiveTest.kt"
    "src/test/kotlin/.../MiniMaxFeaturesLiveTest.kt"
    "src/test/kotlin/.../OpenAIResponsesLiveTest.kt"
)
for f in "${BASELINE_BROKEN_FILES[@]}"; do
    if [ -f "$f" ]; then mv "$f" "$BASELINE_DIR/"; fi
done

restore_baseline() {
    for f in "${BASELINE_BROKEN_FILES[@]}"; do
        mv "$BASELINE_DIR/$(basename $f)" "$f" 2>/dev/null || true
    done
}
trap restore_baseline EXIT

# Now run your verification
./gradlew :TPipe-GenericOpenAI:compileTestKotlin
./gradlew :TPipe-GenericOpenAI:test --tests "*YourNewTest*"
```

The `trap restore_baseline EXIT` runs on every exit path — successful,
interrupted (`SIGINT`), error (`set -e`), or the script's own crash. The
source tree is consistent regardless of how the script ends.

## Pitfall 5 — Gradle's test results cache can hide real failures

When the verification script runs the same `--tests` pattern
back-to-back, Gradle's UP-TO-DATE optimization returns cached "passed"
results from the prior run. The repetition looks like `BUILD SUCCESSFUL`
even when the test JVM didn't actually run anything. Force fresh
executions with `--rerun-tasks` on the first invocation only — subsequent
runs in the same script can rely on the cache once you've confirmed the
first run actually executed.

Verification: the JUnit XML output (`build/test-results/test/TEST-*.xml`)
records the `time` attribute per test. If a test that ran for 1.0s on
the first invocation shows `time="0.001"` on the second, the second
run used the cache and the verification receipt is stale. Re-run with
`--rerun-tasks` to invalidate.

## Worked example: Mantle GPT-5.6 explicit prompt caching (2026-08-03)

The complete trajectory:

1. Added `PromptCacheOptions` + `PromptCacheBreakpoint` data classes to
   `env/`. The breakpoint has `@EncodeDefault(EncodeDefault.Mode.ALWAYS)`
   on its `mode` field — Mantle requires the field to be present.
2. Added `RequestSerializationOptions` data class to `api/`. Widened
   `RequestSerializer.serialize(...)` signature with default
   parameter.
3. Added `MantleGpt56PromptCacheMetadata` + `MantleMetadataKeys` +
   `supportsMantleGpt56ExplicitCaching()` + `requireMantleGpt56ExplicitCachingSupport()`
   to `mantle/`.
4. Updated `OpenAIResponsesRequestSerializer.convert()` to read the
   metadata, validate the (model, apiMode), and emit the wire
   fields. The `AFTER_INSTRUCTIONS` boundary transformation emits a
   `developer`-role input message with the breakpoint marker.
5. Updated `OpenAIRequestSerializer` to forward the new options
   parameter to the Responses delegate — easy-to-miss couple.
6. Added `enableMantleGpt56ExplicitPromptCaching()` extension to
   `mantle/MantleExtensions.kt`.
7. Updated `GenericOpenAIPipe.kt:1137` to pass
   `RequestSerializationOptions(metadata = pipeMetadata as Map<String, Any?>)`
   to the `serialize` call.
8. Created 5 new test classes (24 unit tests) + 4 new cases in
   `OpenAIResponsesRequestSerializerTest` + 1 live test class
   (3 cases, gated on `BEDROCK_MANTLE_GPT56_LIVE_TEST=true`).
9. Wrote `/tmp/hermes-verify-mantle-gpt56-prompt-caching.sh` with the
   stash-and-restore pattern to compile and run the new tests against
   the pre-existing baseline rot.

Result: 114 PASSED, 0 FAILED, 6 SKIPPED across the focused scope
(production compile + new unit tests + serializer regression +
existing Mantle regression + gated live test). Plan, verification
script, and results preserved at
`.hermes/plans/mantle-gpt56-explicit-prompt-caching/plan.md` and
`/tmp/hermes-verify-mantle-gpt56-prompt-caching*`.

## Related references

- `interactive-plan/SKILL.md` Phase 4 verification discipline — affected-module
  baseline vs. full-suite decisions, ad-hoc verification recipes, the
  `hermes-verify-*` script prefix convention.
- `writing-plans/SKILL.md` — the plan-file-side counterpart to this
  reference, for the planning side of TDD-first typed-extension work.
- The Mantle-specific implementation details (gate, serialization
  shape, JSON-rail failure mode) are in `software-development/tpipe-generic-openai/SKILL.md`
  under the "Mantle GPT-5.6 prompt-cache" h3.
