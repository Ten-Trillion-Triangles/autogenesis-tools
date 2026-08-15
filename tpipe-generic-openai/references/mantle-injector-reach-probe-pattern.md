# Mantle Injector-Reach Probe Pattern (round 1, pre-fix, 2026-07-30)

Class-level recipe for verifying whether TPipe system-prompt injectors
(JSON schema rail, middle-prompt injection, footer-prompt injection)
actually reach the wire on Mantle / GenericOpenAIPipe. Applies to any
investigation of "model obeys its contract vs framework injects the
contract" — not just Mantle.

## The diagnostic split — structural probe + live probe

**Structural probe** (no network, fast, runs in every gradle pass):
- Read `pipe.jsonInput`, `pipe.jsonOutput`, `pipe.reasoningPipe`,
  `pipe.pipeMetadata`, `pipe.getSystemPromptText()` directly on the
  factory-returned pipe instance.
- Assert what IS there. Today the assertions FAIL on JSON contract
  presence and PASS on `pipeMetadata["injectMiddlePrompt"] == false`
  (the partial-fix suppression shape).
- Pattern: copy `MantleInjectorReachProbeTest.kt` from
  `server/src/test/kotlin/globals/` in the Autogenesis project.

**Live probe** (gated, runs only when `BEDROCK_MANTLE_LIVE_TEST=true`):
- Hook `preInvokeFunction` on both the host pipe AND the reasoning
  pipe. Capture `content.text` into a `StringBuilder` per pipe.
- Run `pipe.execute(TEST_PROMPT)` against real Mantle with real AWS
  creds.
- Assert that the schema field name (e.g., `verdict`) appears in the
  captured outgoing prompt.
- Pattern: copy `MantleInjectorWireProbeLiveTest.kt` from the same
  directory. Gate pattern is identical to
  `BedrockMantleReasoningBuildersLiveTest.kt`:
  `@EnabledIfEnvironmentVariable(named = "BEDROCK_MANTLE_LIVE_TEST", matches = "true")` + `@TestInstance(PER_CLASS)` + `@BeforeTest installCredentials()` parsing `~/.aws/credentials` into `BedrockMantleEnv.setAccessKeyId/setSecretAccessKey`.

## The schema-field-name pitfall (self-defeating assertion)

Anti-pattern (DO NOT DO THIS):

```kotlin
const val TEST_PROMPT = "Reply with the JSON object matching the schema."
assertTrue(outgoingPrompt.contains("json", ignoreCase = true))
```

The assertion passes because the test prompt itself contains "JSON",
not because any injector fired. This is the self-defeating assertion
trap that hides whether the schema actually reached the wire.

Correct pattern:

```kotlin
const val TEST_PROMPT = "Reply concisely."        // no schema keywords
const val SCHEMA_FIELD = "verdict"               // ONLY an injected rail carries this
assertTrue(outgoingPrompt.contains(SCHEMA_FIELD, ignoreCase = true))
```

## The hermetic verifier pattern

After writing both probes, build a hermetic ad-hoc verifier that:

1. Runs the structural probe and asserts JUnit XML shows the expected
   pre-fix shape (e.g., 7 tests / 0 failures today, where each test
   pins a specific defect).
2. Runs the live probe and asserts JUnit XML shows 2 failures
   (pre-fix state — JSON schema must NOT reach wire).
3. Parses the captured outgoing prompt out of the live XML's
   `system-out` block (HTML-entity decoding first — `&#10;` for
   newlines, `&quot;` for double-quotes).
4. Cross-checks: host outgoing prompt contains ONLY the user prompt,
   reasoning pipe outgoing prompt contains the converse-history JSON
   with an empty developer role.

Authoritative source is JUnit XML at
`server/build/test-results/test/TEST-<fqcn>.xml`, NOT gradle stdout.
Stdout PASSED markers can be lost when tests print heavy stdout (the
live probe dumps the entire outgoing-prompt payload).

The canonical script shape is in the captured
`/tmp/hermes-verify-mantle-injector-reach.summary.txt` (round 1 run,
4/4 PASS):
- `set -u` at the top
- `WORK="$(mktemp -d -t <topic>.XXXXXX)"`
- `SUMMARY="/tmp/hermes-verify-<topic>.summary.txt"`
- `trap cleanup EXIT` removes `$WORK` and self-cleans
- JUnit XML authoritative: `tests=`, `failures=`, `errors=`, `skipped=`
  parsed via `grep -oE 'tests="[0-9]+"' | head -1 | grep -oE '[0-9]+'`
- HTML-entity decoding step before regex-matching captured fragments:
  `sed -e 's/&#10;/ /g' -e 's/&quot;/"/g'`
- Cross-check extracted JSON body separately from assertion message
  text (the assertion message contains the field name, so naive
  substring matching produces false positives)

## Where the wire payload actually goes wrong

The bug report (`docs/bugs/MANTLE_GEMMA_JSON_ADHERENCE.md`) framed
the symptom as "Gemma 4 cutover caused prose/empty responses." The
ACTUAL root cause is upstream of the model:

1. `BedrockConfig.buildMantleAuthorPipe` (Autogenesis
   `server/src/main/kotlin/globals/BedrockConfig.kt:1115-1198`)
   constructs `GenericOpenAIPipe()` directly, never calls
   `requireJsonPromptInjection()`, never calls
   `setJsonOutput(...)`. The system prompt is the raw `author`
   string with no JSON enforcement suffix.
2. `BedrockConfig.buildMantleReasoningPipe` (same file
   `:1312-1349`) does the same. Mantle reasoning pipes built via
   `mantleStructuredCotBuilder()` are attached as
   `reasoningPipe` on hosts (passFailAgent.kt:295, nemesisAgent.kt:140)
   but the schema rail never flows through because
   `pipeMetadata["injectMiddlePrompt"]` is `false` (the partial-fix
   suppression at GenericOpenAIPipe.kt:670-671).
3. The legacy Qwen path works because it goes through
   `BedrockConfig.ReasoningSettings` constructor (`:658-666`) which
   sets `ReasoningMethod.RolePlay` and wires the schema rail
   unconditionally.

Live capture (pre-fix, Mantle/E2B, host with `setJsonOutput(ProbeJson::class)`):

- Host outgoing prompt: literally just `"Reply concisely."` — 17 chars.
- Reasoning pipe outgoing prompt: converse-history JSON with EMPTY
  developer role (`"text": "  "`) and the user prompt. Zero schema.

The model returns the user prompt unchanged because there is nothing
else in the prompt to work with.

## Cross-references

- The Autogenesis probe source files:
  `server/src/test/kotlin/globals/MantleInjectorReachProbeTest.kt`
  and `server/src/test/kotlin/globals/MantleInjectorWireProbeLiveTest.kt`
- The captured wire payload evidence:
  `server/build/test-results/test/TEST-globals.MantleInjectorWireProbeLiveTest.xml`
- The bug report being verified:
  `docs/bugs/MANTLE_GEMMA_JSON_ADHERENCE.md`
- The legacy Qwen / ReasoningSettings constructor that does the right
  thing: `server/src/main/kotlin/globals/BedrockConfig.kt:658-666`
- The Mantle wire-format completion hook with three early-return gates:
  `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:407-414`
- The Mantle `configureBedrockMantle` partial-fix at
  `GenericOpenAIPipe.kt:666-671` (writes metadata keys as `false`,
  suppressing the feature)
