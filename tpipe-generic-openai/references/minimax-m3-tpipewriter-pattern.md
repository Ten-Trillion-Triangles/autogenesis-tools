# MiniMax-M3 Generic OpenAI Refactor of TPipeWriter

Worked example of a hard-cutover provider migration. The `GenericAI` branch
of TPipeWriter replaced AWS Bedrock with GenericOpenAIPipe targeting MiniMax-M3
in a single refactor commit, mirroring the OpenRouter branch's pattern.

## When this pattern fits

- You're migrating a TPipe application from one LLM provider to another
- The new provider has an OpenAI-compatible endpoint (`/v1/chat/completions`
  or `/v1/responses`)
- You want a hard cutover (not multi-provider abstraction)
- You have a single target model on the new provider (single-model edition)
- The TPipe library already ships a `GenericOpenAIPipe` for your target

## Provider mapping decisions

| Old (Bedrock) | New (MiniMax-M3 Generic OpenAI) | Why |
|---|---|---|
| `BedrockMultimodalPipe` / `BedrockPipe` | `GenericOpenAIPipe` | Different provider, same TPipe pattern |
| Bedrock ARN model IDs (`anthropic.claude-sonnet-4-...`) | MiniMax model name (`MiniMax-M3`) | Hosted model, no ARN |
| AWS region (`us-east-2`) | None — `https://api.minimax.io/v1` | Hosted, regionless |
| `bindInferenceProfile("model", "arn:...")` calls | Removed — no-op | No ARN binding needed |
| `setRegion()`, `useConverseApi()`, `enableCaching()` | Dropped entirely | Bedrock-specific; M3 has no equivalent |
| `setReadTimeout()` | Dropped | Bedrock-only; GenericOpenAIPipe has internal 120s default |
| AWS credential env vars | `MINIMAX_API_KEY` | New auth model |
| `Env.init()` builds `bedrockEnv.bindInferenceProfile(...)` cascade | `Env.init()` wires `genericOpenAIEnv.setApiKey(MINIMAX_API_KEY)` | One-line setup |

## The surgical refactor in 9 commits (matching OpenRouter pattern)

```
chore(deps): swap TPipe-Bedrock for TPipe-GenericOpenAI
refactor(model-config): collapse to single MiniMax-M3, no-op init()
refactor(env): strip Bedrock pipes from Env.kt
refactor(pipelines): strip Bedrock from all Builders/* + MiniMaxReasoning adapter
refactor(shell/settings/util/main): strip Bedrock references
test(minimax): add live smoke + streaming tests, drop NovaTest
docs: rewrite README
fix(env): wire MINIMAX_API_KEY before pipeline construction (lazy pitch-slide)
chore(shell): rename exampleBedrockPipe → exampleGenericOpenAIPipe
```

Each commit is self-contained and the diff is reviewable. Critical: do NOT
batch all changes into one giant commit — the operator (or you, on a later
session) will not be able to bisect or revert cleanly.

## File-by-file change shape

### `build.gradle.kts`
```kotlin
// Before
implementation("com.TTT:TPipe-Bedrock:1.0.0")
// After
implementation("com.TTT:TPipe-GenericOpenAI:1.0.0")
```

### `Globals/ModelConfig.kt`
- Collapse all 17 model-id variables (`deepseekModelName`, `claudeModelName`,
  `qwenCoder480B`, etc.) to a single constant string `"MiniMax-M3"`.
- `init()` becomes a no-op (no ARN bindings).
- Variable NAMES preserved — call sites in Env.kt / Builders/* don't need
  renaming, just the values change. Saves hundreds of call-site updates.

```kotlin
const val deepseekModelName = "MiniMax-M3"
const val claudeModelName = "MiniMax-M3"
// ... all 17 collapsed
const val MiniMaxContextWindowSize: Int = 512000  // 512K for M3

fun init() {
    // No-op — MiniMax is hosted, no ARN binding
}
```

### `Globals/Env.kt`
- Every `val <name> = BedrockMultimodalPipe()` becomes:
  ```kotlin
  val <name> = GenericOpenAIPipe()
      .setBaseUrl("https://api.minimax.io/v1")
      .setApiKey(genericOpenAIEnv.resolveApiKey())
      .setApiMode(ApiMode.OpenAIResponses)
      .setModel(ModelConfig.primaryModelName)
      .setContextWindowSize(512000)
      // ... pipe-specific setters ...
  ```
- Drop all `setRegion(...)`, `useConverseApi()`, `enableCaching()`,
  `setReadTimeout(...)` calls.
- Bump context windows < 512K to 512000 (MiniMax-M3 has 512K context).
- Wire `MINIMAX_API_KEY` to `genericOpenAIEnv.setApiKey()` BEFORE the first
  `buildNccWriter(...)` call (see Pitfall above).

### `Builders/*.kt` — same pattern, ~10 files

Same surgical rewrite: `BedrockMultimodalPipe()` → `GenericOpenAIPipe()`
chain with the four-line setup preamble, drop Bedrock-only setters, bump
context window. `reasonWithBedrock(...)` calls in `ReasoningBuilders.kt`
become `reasonWithMiniMax(...)`.

### `Builders/MiniMaxReasoning.kt` (new)

Mirrors `OpenRouterReasoning.kt` but forces reasoning OFF (MiniMax-M3 is
the no-reasoning variant). Two-knob disable:
```kotlin
pipe.disableReasoning()  // base Pipe.useModelReasoning flag
// ReasoningConfig.enabled = false (set in wire payload)
```

Migration to MiniMax-M2.7 (which DOES support reasoning): delete the
`pipe.disableReasoning()` call. One-line change.

### `Shell/*.kt`, `Util/StreamingUtil.kt`, `Structs/WriterSettings.kt`

- `Shell/Shell.kt`: 6 template pipes → `GenericOpenAIPipe()` with `.truncateModuleContext()`
- `Shell/SettingsSubshell.kt`: collapse 16-model selector menu to single
  MiniMax-M3 entry; drop `getRegionV2()` calls (regionless).
- `Util/StreamingUtil.kt`: actually wire streaming via
  `pipe.setStreamingEnabled(true)` + `pipe.setStreamingCallback(callback)`.
  The previous Bedrock-era version was a no-op that only counted pipes.
- `Structs/WriterSettings.kt`: drop `setRegion()`/`getRegionV2()` member
  functions (Bedrock-era region-resolution logic); add
  `MiniMaxContextWindowSize = 512000` constant.

### Tests

Add three test files following the OpenRouterSmokeTest pattern:

```kotlin
class MiniMaxSmokeTest {
    @Test
    fun testMiniMaxConnection() {
        assumeTrue(System.getenv("MINIMAX_API_KEY")?.isNotBlank() == true,
                   "MINIMAX_API_KEY not set; skipping smoke test")
        val pipe = GenericOpenAIPipe()
            .setBaseUrl("https://api.minimax.io/v1")
            .setApiKey(GenericOpenAIEnv.resolveApiKey())
            .setApiMode(ApiMode.OpenAIResponses)
            .setModel("MiniMax-M3")
            .setMaxTokens(256).setTemperature(0.0)
        runBlocking {
            pipe.init()
            val out = pipe.execute(MultimodalContent().apply { text = "Hello" })
            assertTrue(out.text.isNotBlank())
        }
    }
}
```

Delete the Bedrock live test (`NovaTest.kt`).

## Verification recipe

1. `./gradlew clean build` → BUILD SUCCESSFUL
2. `./gradlew test` → all tests pass with live tests gated on `MINIMAX_API_KEY`
3. End-to-end TUI test via tmux: `./run.sh`, exercise each `/command`,
   check no crashes in captured pane
4. **Parse the trace file** at `~/.TPipe-Debug/traces/*.html` and verify
   `grep -c PIPE_FAILURE` returns 0. Even if the TUI looks fine, an agent
   pipeline can silently recover from a failure by replacing the pipe
   output. Trace inspection is the only way to confirm zero failures.

The user's rule for TUI verification: "make sure you use the tpipe trace
parsing skill... if an agent crashes it will just continue onward here in
many cases. So check the trace files for sure as well."

### TUI verification — drive EVERY command, don't spot-check

The user pushed back hard on the first verification pass: "I'm not sure
you've tested eerything at this stagee." That caught a real bug — spot-checking
4 of 24 `/help` commands missed two genuine regressions. The workflow that
actually works:

1. **Enumerate every command** from `/help` output. There are 24+.
2. **Build a tmux script** that sends each command, waits N seconds (longer
   for LLM-driven commands like `/write`, `/idea`, `/chat`, `/rewrite`),
   captures the result. Example: `/tmp/tpw_full_test.sh` ran 30 scenarios.
3. **Restart the TUI fresh** before the script so the trace file is clean
   for parsing afterward.
4. **Trace parser + grep for FAILURE** events after the script. The trace
   filename contains a hash that changes per restart (e.g.
   `trace-57cb0ee7-html.html`), so find the latest file via `ls -t`.
5. **Check `/llm-settings` status** for every pipe to confirm model names
   actually resolved to the expected value (catches local-variable-shadow
   bugs that wouldn't show up in compile errors).
6. **Verify persistence** — `/save`, `/export`, `/load`, `/settings`
   actually write to disk and round-trip. Don't trust "looks right in TUI" —
   `ls -la ~/.TPipeWriter/` and `stat <file>`.

**Tmux capture technique** (the only way to read scrollback):
```bash
tmux capture-pane -t <session> -p -S -N   # -N = last N scrollback lines
```
Without `-S`, you only see the current viewport. For deep scrollback use
`-S -200` or higher.

**For hangs** the user suggested JDWP attach with debug symbols. Add to your
test script:
```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005 \
     -jar build/libs/TPipeWriter-1.0.0-all.jar
```
Then `mcp_jdwp_debug_attach` from a separate call. Note: shadowJar strips
debug symbols by default — for unobfuscated stack traces, build without
shadowJar (`./gradlew installDist` produces an unpacked distribution with
real class names).

## Common mistakes during the refactor

1. **Trusting comments inside Kotlin `/** ... */` blocks.** The line
   `* Env.kt and the Builders/* pipelines does not need its call sites`
   contains the literal sequence `/*` inside the comment text — Kotlin
   treats this as the START of a NESTED comment and the entire `*/`
   end-of-block is consumed. Symptom: "Unclosed comment" pointing at
   the file's closing brace. **Fix**: avoid `/*` inside prose comments.
   Use "Builders pipelines" or "Builders slash-star pipelines" instead.

2. **Forgetting to add the `import Globals.ModelConfig` after replacing
   `ModelConfig.X` references with `Globals.ModelConfig.X`.** The fully-
   qualified reference works fine; only the bare `ModelConfig.X` requires
   the import. Pick one convention per file.

3. **Leaving a `: GenericOpenAIPipe` type annotation on a fluent chain that
   includes `.setModel(...)`.** This compile-error class is non-obvious
   because the annotation looks like it should help. It doesn't. Drop the
   annotation (let type inference do its job) OR split the chain at
   `setModel()`.

4. **Constructing the pipeline at the object-level field declaration
   site.** This fires the static initializer before `Main.kt` runs, so the
   `MINIMAX_API_KEY` env var wiring is too late. Use `by lazy { ... }`
   for fields whose construction calls `pipe.init()`.

5. **Forgetting to delete `setRegion()` member functions on
   `ModelSettings` (or other Bedrock-era fields that reference removed
   providers).** Kotlin won't flag these — they become harmless no-ops.
   But the SettingsSubshell UI will still call them. Drop them at the
   same time as the rewrite.

6. **Bulk-regex pass leaving a second `.setModel(bareLocalVar)` call after
   the first `.setModel(ModelConfig.primaryModelName)`.** A common pattern
   in pipe chains is `setModel(X).setModel(Y)` where the second call was
   meant to override. If your regex pass substitutes `ModelConfig.X` for
   `X` (qualified form only) but misses bare `X` references that resolve
   to a local file-scope `val <X> = "old-bedrock-model-id"`, you'll end up
   with a duplicate call where the second one uses the local var and
   RESETS the model back to a Bedrock-era ID. Symptom: `/llm-settings`
   status shows `Model: openai.gpt-oss-20b-1:0` (or whatever the local
   var says) on some pipes. Fix: dedupe the `.setModel(...)` chain so
   there's only ONE call per pipe. **After ANY bulk-rewrite pass, run a
   grep across the codebase for `.setModel(bareVar)` and verify each
   `bareVar` either resolves to `Globals.ModelConfig.X` or is removed.**

7. **`ApiMode` and `GenericOpenAIEnv` import path gotchas.** After a bulk
   pass, the imports `import genericOpenAIPipe.ApiMode` and
   `import env.genericOpenAIEnv` may have been written based on a stale
   skill that assumed flat package structure. The correct paths are
   `genericOpenAIPipe.api.ApiMode` and `genericOpenAIPipe.env.GenericOpenAIEnv`.
   Use `import genericOpenAIPipe.env.GenericOpenAIEnv as genericOpenAIEnv`
   to preserve call-site ergonomics. See the parent skill's "Pitfall: Wrong
   import paths" section.

## MiniMax-M3 incompatibility with Bedrock-era JSON-mode surgical-change pipes

Real finding from TPipeWriter verification: pipes that were tuned for
Bedrock's structured-output behavior do not survive the cutover to
MiniMax-M3 unchanged. The failure pattern:

1. Pipe configured with `setJsonOutput(SurgicalChangeList())` +
   `requireJsonPromptInjection(stripExternalText = true)` — expects the
   model to emit `{"changeList": [...]}` JSON.
2. MiniMax-M3 emits **prose** instead (4625-char output for a "forest
   at dawn" prompt). The system prompt and footer instruct "Output only
   JSON" but M3 ignores it.
3. `stripExternalText` strips everything outside the JSON envelope,
   leaving `content.text` empty.
4. `shouldTerminate() = isEmpty() || terminatePipeline` returns true.
5. VALIDATION_FAILURE fires.

**Pipes affected**: `post writer pipe`, `cleanup step two pipe` in
TPipeWriter (any pipe configured with `setJsonOutput(...) +
requireJsonPromptInjection(stripExternalText = true)`).

**Impact**: zero on user-visible content, because every affected pipe
already has an `onFailure` callback that restores the previous prose
from the context bank:
```kotlin
.setOnFailure { _, processed ->
    processed.text = ContextBank.getContextFromBank("new page")
        .contextElements.lastOrNull() ?: processed.text
    processed
}
```
Verified end-to-end: `/write "A quiet forest at dawn."` followed by
`/export final` produced a 4249-char `final.txt` containing the full prose.

**Fix options** (pick whichever fits the use case):
- Add JSON-mode to the system prompt: "Your response MUST be valid JSON
  matching the schema below. Do NOT include any prose, explanations, or
  commentary — output ONLY the JSON object." — may not work with M3.
- Drop `stripExternalText = true` — let the prose through, extract the
  JSON from the response with `repairAndDeserialize()` if available.
- Drop `setJsonOutput(...)` entirely — change the pipe's role to
  prose-only.
- Replace the LLM-driven surgical change with a deterministic text
  transformation function (no LLM call).

The onFailure recovery is the right behavior for graceful degradation;
the validation failures are informational, not crashes. But if you
want zero `VALIDATION_FAILURE` events in your trace, you need to pick
one of the above fixes.

## Result (TPipeWriter GenericAI branch — 11 commits, ~3 hours)

- All 44 source files compile cleanly
- 68 tests pass (25 unit + 2 live + 41 existing)
- Live MiniMax-M3 calls verified via both smoke test and TUI
- 367-event trace shows 0 unhandled exceptions across 22 pipes exercised
- 4 graceful VALIDATION_FAILURE events on JSON-mode surgical-change
  pipes, all recovered via onFailure callbacks
- Single commit per file-class (model config, env, pipelines, settings, etc.)
- README rewritten following OpenRouter branch structure
- Comprehensive TUI test report at `TUI_TEST_REPORT.md` (in the
  repo root) documenting every command exercised, every failure found,
  and the resolution.