# Wire-reach investigation reference

Session-applied reference for "does pipe-level feature X actually reach the model wire?" investigations. Companion to `tpipe-pipe-internals` SKILL.md "Pipe-state probes for 'does X reach the wire?' investigations" section.

## When this applies

Investigation triggered by any of:
- "the model isn't obeying X"
- "the wire payload doesn't have X"
- "injector Y is supposed to reach Z"
- "schema rail missing"
- "JSON-mode enforcement failed"

## Three-surface audit (always capture all three)

| Surface | How to capture | What lives here |
|---|---|---|
| User role | `preInvokeFunction { content -> captured.append(content.text); true }` | The user's prompt (plain text) |
| System role | `val sysAfter = pipe.getSystemPromptText()` after `execute()` | JSON schema rail, footer prompt, middle-prompt injection, context blocks |
| Wire body | HTTP intercept (WireMock / `HttpURLConnection` fixture) | `response_format` field, request headers, body serialization |

If you capture only the user role, you WILL conclude "the JSON rail didn't reach the wire" — but it actually lives on the system role and was injected correctly. Always check the system role too.

## Mantle / Gemma 4 case study (2026-07-30)

Investigation: "Gemma 4 / Mantle pipes emit prose where JSON is expected; is it a model issue or a TPipe wiring issue?"

### Three probes that resolved it

1. **Structural probe** (`MantleInjectorReachProbeTest.kt`, 7 tests, no network) — instantiate `mantleAuthorBuilder31B(...)` and `mantleStructuredCotBuilder(...)`, read `pipe.jsonOutput` / `pipe.jsonInput` / `pipe.pipeMetadata` / `pipe.reasoningPipe` / `pipe.getSystemPromptText()`. **Found**: factories skip `requireJsonPromptInjection` and `setJsonOutput` entirely. Zero JSON contract wiring at the factory level.

2. **Live wire probe** (`MantleInjectorWireProbeLiveTest.kt`, 3 tests, network-gated on `BEDROCK_MANTLE_LIVE_TEST=true`) — wire `preInvokeFunction` to capture `content.text`, run `pipe.execute(testPrompt)`, also capture `pipe.getSystemPromptText()` post-execute. **Found**: user prompt arrives as just `Reply concisely.` (17 chars). Reasoning pipe's wire payload (converse-history JSON) has empty developer role. **BUT** when the test wires `requireJsonPromptInjection + setJsonOutput` at the agent layer (mirroring `railroadAgent.kt:38-39` for Bedrock), the system prompt carries the full JSON rail:
   ```
   You must return your output only in Json format...
   The json output schema is as follows: {
       "verdict": "example_string",
       "note": "example_string"
   }
   ```

3. **Working-control probe** — found `mantle validator pipe` works because its host is `BedrockMultimodalPipe` (NOT Mantle factory), wired at agent layer. Mapped the asymmetry: working case = factory bypassed the Mantle builder entirely; failing case = Mantle builder called directly without JSON contract wiring.

### Decision tree result

Control wires JSON contract at agent layer; failing cases skip it at Mantle factory layer → **fix is in autogenesis factory**, NOT in TPipe.

TPipe-side investigation found F3 was a non-bug: `GenericOpenAIPipe.onApplySystemPromptComplete` (`:407-414`) correctly populates `responseFormat` when called, and the system-prompt JSON augmentation at Pipe.kt:2108-2257 fires when `supportsNativeJson = false`. The Mantle hook was never the problem.

### Partial-fix residue (2026-07-30 commit 6edb2a01)

A previous agent added `configureBedrockMantle` to GenericOpenAIPipe.kt that sets:
- `pipeMetadata["injectMiddlePrompt"] = false`
- `pipeMetadata["injectFooterPrompt"] = false`

The KDoc claimed this "mirrors `ReasoningBuilder.assignDefaults`" — false. It only writes 2 of the 7 metadata keys `assignDefaults` writes, AND sets them to literal `false` instead of `ReasoningSettings` defaults. Result: NPE at Pipe.kt:8033/8047 is gone (keys exist, cast succeeds, returns `false`, no exception) but middle/footer prompt injection is suppressed.

**Lesson**: when investigating "did the previous fix work?", check the KDoc claims against the actual code. KDoc-overstating-implementation is a class of bug worth flagging.

## Verifier pattern (`/tmp/hermes-verify-mantle-injector-reach.sh`)

Hermetic shell script pattern for running multiple probes end-to-end with PASS/FAIL summary. Structure:

```bash
set -u
WORK="$(mktemp -d -t <topic>.XXXXXX)"
SUMMARY="/tmp/hermes-verify-<topic>.summary.txt"
trap cleanup EXIT  # rm -rf $WORK

ts() { date +"%Y-%m-%dT%H:%M:%S"; }
PASS_COUNT=0
FAIL_COUNT=0
check_pass() { PASS_COUNT=$((PASS_COUNT+1)); printf '[%s] PASS: %s — %s\n' "$(ts)" "$1" "$2" | tee -a "$SUMMARY"; }
check_fail() { FAIL_COUNT=$((FAIL_COUNT+1)); printf '[%s] FAIL: %s — %s\n' "$(ts)" "$1" "$2" | tee -a "$SUMMARY"; }

# Per check:
./gradlew :server:test --tests "<FQCN>" --rerun-tasks > "$WORK/<test>.log" 2>&1
XML="$PROJECT/server/build/test-results/test/TEST-<FQCN>.xml"
tests=$(grep -oE 'tests="[0-9]+"' "$XML" | head -1 | grep -oE '[0-9]+')
failures=$(grep -oE 'failures="[0-9]+"' "$XML" | head -1 | grep -oE '[0-9]+')
errors=$(grep -oE 'errors="[0-9]+"' "$XML" | head -1 | grep -oE '[0-9]+')
# Cross-check captured payload (handle HTML-entity-encoded XML)
sed -e 's/&#10;/ /g' -e 's/&quot;/"/g' "$XML" > "$WORK/<test>.plain.xml"
grep -oE "<expected-fragment>" "$WORK/<test>.plain.xml"
```

Key points:
- JUnit XML is the source of truth (stdout `PASSED` markers can be lost when tests print heavy stdout)
- HTML entities in XML (`&#10;` for newline, `&quot;` for double-quote) need decoding before regex matching
- Capture the expected pre-fix shape in the assertion (today's "schema NOT in payload" IS the success criterion for a pre-fix verifier)
- Self-clean via `trap cleanup EXIT`

## Test scaffolds to copy

For the structural probe (no network, instant):

```kotlin
@BeforeTest fun installBearerCredentials() { GenericOpenAIEnv.setApiKey("test-key-not-used-for-network") }

@Test fun `factory leaves jsonOutput blank at the factory level`() {
    val pipe: Pipe = BedrockConfig.mantleAuthorBuilder31B(author = "...", showThinking = false)
    assertTrue(pipe.jsonOutput.isBlank(), "factory must not pre-wire jsonOutput")
}
```

For the live probe (gated, ~1 min/run):

```kotlin
@EnabledIfEnvironmentVariable(named = "BEDROCK_MANTLE_LIVE_TEST", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MantleWireProbeLiveTest {
    private fun installCredentials() {
        assumeTrue(credentialsFile.exists(), "Skipping because credentials missing")
        // parse ~/.aws/credentials, install into BedrockMantleEnv
    }
    private fun clearCredentials() {
        BedrockMantleEnv.clearAccessKeyId(); BedrockMantleEnv.clearSecretAccessKey()
    }

    @Test fun `Mantle host pipe with setJsonOutput reaches wire-format hook`() = runBlocking {
        installCredentials()
        try {
            val pipe = GenericOpenAIPipe().apply {
                setBedrockMantle(BedrockConfig.mantleRegion(), BedrockConfig.mantleModelId("gemma4ModelId"))
                requireJsonPromptInjection()
                setJsonOutput(MyJson::class)
            }
            pipe.init()
            pipe.execute("test prompt")
            val sysAfter = pipe.getSystemPromptText()
            assertTrue(sysAfter.contains("verdict"), "JSON rail must reach pipe.systemPrompt")
        } finally { clearCredentials() }
    }
}
```

Run with:
```bash
BEDROCK_MANTLE_LIVE_TEST=true \
BEDROCK_AWS_PROFILE=default \
BEDROCK_AWS_CREDENTIALS_FILE=/home/cage/.aws/credentials \
./gradlew :server:test --tests "<FQCN>" --rerun-tasks
```

## Composability with TPipe Mantle bugs

This reference was created during investigation of `docs/bugs/MANTLE_GEMMA_JSON_ADHERENCE.md` and `BUG_INJECTMIDDLEPROMPT_GEMMA.md` (the latter file does NOT exist in the workspace — the actual file is `docs/bugs/MANTLE_GEMMA_JSON_ADHERENCE.md`; the bug-name referenced in the report at line 218 is a separate handoff doc that was never committed). Two memory entries are relevant for cross-session continuity:

- "TPipe reasoning-pipe metadata contract (verified 2026-07-30)" — describes the `pipeMetadata["injectMiddlePrompt"]` / `injectFooterPrompt` contract and the unguarded-cast risk at Pipe.kt:8033/8047
- "Mantle credentials bootstrap gap (production-side, autogenesis 2026-07-30)" — `AwsCredentialsBootstrap.kt:31` doesn't mirror credentials into `BedrockMantleEnv`, blocking live verification of any Mantle fix in production

Future session picking up this thread should:
1. Land the autogenesis-side F1+F2 fix on `buildMantleAuthorPipe` / `buildMantleReasoningPipe` (BedrockConfig.kt:1115-1198 and 1312-1358) — add `requireJsonPromptInjection + setJsonOutput` at the factory level
2. Close the credentials bootstrap gap before live verification of any Mantle fix in production
3. Run the verifier `/tmp/hermes-verify-mantle-injector-reach.sh` to flip the pre-fix 2 failures to post-fix passes
