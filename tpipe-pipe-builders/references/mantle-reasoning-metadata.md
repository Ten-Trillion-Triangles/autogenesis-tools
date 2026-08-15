# Mantle reasoning-pipe metadata contract

Mantle reasoning pipes built via `GenericOpenAIPipe.setBedrockMantle(...)`
must satisfy the same reasoning-pipe metadata contract that the four
first-party builders (`reasonWithBedrock`, `reasonWithOllama`,
`reasonWithOpenRouter`, `reasonWithGenericOpenAI`) provide through
`ReasoningBuilder.assignDefaults`. This reference documents the contract,
the construction-time wiring that makes Mantle first-class, and the
3-layer TDD verification recipe that proves it.

## Why this matters

Reasoning-pipe middle/footer prompt injection at `Pipe.kt:8033` /
`Pipe.kt:8047` reads two metadata keys:

```kotlin
val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as? Boolean ?: false
val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as? Boolean ?: false
```

When the keys are absent and the cast was the original `as Boolean`,
the result was `NullPointerException: null cannot be cast to non-null
type kotlin.Boolean`. The four first-party builders populated the keys
via `ReasoningBuilder.assignDefaults` (`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:317-318`).
Mantle reasoning pipes bypassed that helper, so every Mantle reasoning
invocation historically threw NPE → retry absorption → degraded output
(empty `{}` JSON from schema-strict agents, permissive `isValid: true`
from validators). The contract is provider-agnostic; Mantle is a
TPipe provider like any other.

## The two-layer fix

The fix is two layers, both required:

### Layer 1 — cast safety at `Pipe.kt:8033/8047`

Replace `as Boolean` with `as? Boolean ?: false`. Defense in depth.
Closes the NPE for any current or future reasoning-pipe constructor
that omits the metadata keys. Matches the surrounding `as?` idiom
already used 6 times in `Pipe.kt` (lines 5998, 7070, 7082, 7086,
7436, 7632) and the guarded pattern at `Pipe.kt:7166-7168` /
`Pipe.kt:7208-7210` for `reinforceSystemPrompt`.

This layer alone is not the goal — it silently degrades the feature
to "no injection" on Mantle. Mantle-shaped pipes without the
metadata would return `""` from both getters, which is a feature
regression, not a crash. Layer 2 is what restores Mantle to
first-class behavior.

### Layer 2 — Mantle structural wiring at construction time

In `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`,
`configureBedrockMantle(config)` is the single internal helper that
all three public Mantle entry points (`setBedrockMantle`,
`setBedrockMantleWithResponses`, `setBedrockMantleAuth`) route through.
Writing the metadata here populates the contract for every Mantle pipe
this repo produces:

```kotlin
private fun configureBedrockMantle(config: BedrockMantleConfiguration)
{
    setBaseUrl(config.endpoint())
    setApiMode(config.apiMode)
    setModel(config.modelId)

    // Reasoning-pipe metadata contract — mirrors ReasoningBuilder.assignDefaults
    // (TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:317-318).
    // Defaults to false to match ReasoningSettings.injectMiddlePrompt = false.
    pipeMetadata["injectMiddlePrompt"] = false
    pipeMetadata["injectFooterPrompt"] = false

    // ... existing auth resolution ...
}
```

`pipeMetadata` is `MutableMap<Any, Any>` declared at `Pipe.kt:1767`, so
any caller can override the defaults after construction with the
same assignment shape the four first-party builders use internally:

```kotlin
val reasoningPipe = GenericOpenAIPipe()
    .setBedrockMantle(region = "us-east-2", modelId = "google.gemma-4-31b")
reasoningPipe.pipeMetadata["injectMiddlePrompt"] = true  // opt in to injection
```

The construction-time defaults match the documented
`ReasoningSettings.injectMiddlePrompt = false` /
`injectFooterPrompt = false`. A caller who wants injection overrides
the keys explicitly. Mantle reasoning pipes carry the same contract
shape as Bedrock / Ollama / OpenRouter / GenericOpenAI reasoning
pipes — provider-agnostic feature parity.

## Three-layer TDD verification

The fix is verified across three test classes, one per layer:

### Layer A — cast safety
File: `src/test/kotlin/Pipe/PipePromptInjectionReasoningTest.kt`
(10 tests in the base module).

Coverage: null reasoning pipe, absent key, explicit `true`, explicit
`false`, wrong-type (`"true"` string) — same five cases for both
`getMiddlePromptForReasoning()` and `getFooterPromptForReasoning()`.

RED check (pre-fix): absent-key cases throw
`NullPointerException` at `Pipe.kt:8033 / 8047`; wrong-type cases
throw `ClassCastException`. JUnit XML reports `tests="10" failures="4" errors="0"`.

GREEN check (post-fix): JUnit XML `tests="10" failures="0" errors="0"`.

### Layer B — Mantle structural
File: `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/GenericOpenAIPipeMantleMetadataTest.kt`
(4 tests).

Coverage: `setBedrockMantle` populates the keys, `setBedrockMantleWithResponses`
populates the keys, Mantle pipe attached via `setReasoningPipe` does
not throw NPE on either getter, Mantle pipe with `injectMiddlePrompt=true`
override injects the configured text.

RED check (verify by temporarily reverting the structural fix in
`configureBedrockMantle`): JUnit XML reports 2 of 4 failures on the
metadata-presence assertions. The "does not throw NPE" assertion
still passes because Layer A's cast safety absorbs the absent key.
This is the layered design — neither layer alone is sufficient.

GREEN check (post-fix): JUnit XML `tests="4" failures="0" errors="0"`.

### Layer C — provider-agnostic parity
File: `TPipe-Defaults/src/test/kotlin/Defaults/reasoning/ReasoningBuilderParityTest.kt`
(5 tests).

Coverage: each of the four first-party builders
(`reasonWithBedrock`, `reasonWithOllama`, `reasonWithOpenRouter`,
`reasonWithGenericOpenAI`) populates the metadata contract; a direct
call to `ReasoningBuilder.assignDefaults(settings, pipeSettings, targetPipe)`
also populates it. Mantle is not in this test class — Mantle lives in
`TPipe-GenericOpenAI` (Layer B). The four first-party builders exist
to prove the contract is honored across the canonical wiring path; if
any of them regresses (e.g. a refactor drops the assignment block at
`ReasoningBuilder.kt:317-318`), this test catches it loudly.

GREEN check: JUnit XML `tests="5" failures="0" errors="0"`.

### Optional Layer D — live Mantle smoke

File: `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/InjectMiddlePromptLiveMantleTest.kt`
(2 tests, gated by `INJECT_MIDDLE_PROMPT_LIVE_TEST=true`).

Coverage: Mantle-shaped pipe's metadata contract is satisfied end-to-end
through the public API; caller can opt in to middle/footer injection by
overriding the metadata keys.

The live smoke is gated and does NOT require AWS credentials to run —
the metadata is populated inside `configureBedrockMantle` before any
network call. The wire-traffic shape of Mantle is verified separately
by `BedrockMantleLiveTest` (gated by `BEDROCK_MANTLE_LIVE_TEST=true`
with AWS credentials).

## Hermetic verifier

A re-runnable shell script captures the four JUnit XML attributes and
the two source-code patches:

```bash
bash /tmp/hermes-verify-inject-middle-prompt-fix.sh
```

Output:

```
[1/4] running unit + structural + parity tests
[2/4] JUnit XML attribute checks
PASS: TPipe-GenericOpenAI/build/test-results/test/TEST-genericOpenAIPipe.GenericOpenAIPipeMantleMetadataTest.xml tests="4" skipped="0" failures="0" errors="0"
PASS: TPipe-Defaults/build/test-results/test/TEST-Defaults.reasoning.ReasoningBuilderParityTest.xml tests="5" skipped="0" failures="0" errors="0"
PASS: build/test-results/test/TEST-com.TTT.Pipe.PipePromptInjectionReasoningTest.xml tests="10" skipped="0" failures="0" errors="0"
[3/4] cast-safety patch at Pipe.kt:8033,8047
PASS:
    8033:        val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as? Boolean ?: false
    8047:        val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as? Boolean ?: false
[4/4] Mantle structural fix in configureBedrockMantle
PASS:
    660:        pipeMetadata["injectMiddlePrompt"] = false
    661:        pipeMetadata["injectFooterPrompt"] = false

ALL PASS — bug fix verified across cast-safety, structural, and parity layers
```

Source of truth is the JUnit XML attributes (`tests`, `skipped`,
`failures`, `errors`), not the gradle stdout `PASSED` markers — stdout
can drop `PASSED` lines when tests produce heavy stdout output. JUnit
XML is hermetic and survives the daemon-collision noise that gradle
stdout can mask.

## Red→green discipline for structural fixes

When adding a structural fix, the verification step must include a
"would this test catch the bug if I removed the fix" assertion, not
just "does the test pass with the fix in place." Concrete recipe:

1. Run the new test class GREEN with the fix in place.
2. Temporarily revert the structural fix (replace the added metadata
   assignment block with a comment).
3. Run the test class again. Confirm the test class reports the
   expected RED count — the metadata-presence assertions should fail
   with the exact reason the test name describes.
4. Restore the structural fix. Run the test class again. Confirm
   GREEN.

If step 3 does not show the expected RED count, the test is not
actually verifying the structural fix — it's verifying something else
(typically the cast-safety layer absorbing the bug). Tighten the test
or add a new assertion that fails specifically on the structural
absence.

## When to apply this pattern

- Adding a new reasoning-pipe builder for a new provider. The builder
  MUST call `ReasoningBuilder.assignDefaults` OR inline the metadata
  contract keys directly. Either shape satisfies the contract; the
  in-repo builder path is preferred when the consumer module depends
  on `TPipe-Defaults` already (typical).
- Auditing an existing provider builder that bypasses `assignDefaults`.
  Symptom: `Pipe.kt:8033/8047` casts throw NPE on reasoning pipes
  built through this provider. Fix is the same — wire
  `assignDefaults` or inline the keys.
- Reviewing a refactor that touches `ReasoningBuilder.assignDefaults`
  or the four first-party builders. The provider-parity test class
  (Layer C above) catches regressions on the four first-party builders
  but not on new builders — audit any new reasoning-pipe builder for
  the same shape.

## Out of scope for the in-repo fix

The autogenesis consumer-repo Mantle builders
(`server/src/main/kotlin/globals/BedrockConfig.kt:1116-1350` per
bug reports naming those line ranges) construct reasoning pipes
directly via `GenericOpenAIPipe().setBedrockMantle(...)` patterns
that already pass through the public API this fix covers. If the
consumer repo has any builder that constructs a Mantle-shaped pipe
WITHOUT going through `setBedrockMantle` (e.g. via direct
`GenericOpenAIPipe()` construction with later auth wiring), the
consumer-repo builder itself must wire the metadata contract inline
or call `ReasoningBuilder.assignDefaults`. The in-repo fix does not
reach consumer-repo builders; audit those separately.
