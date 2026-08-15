# Reasoning-Pipe Metadata NPE — Autogenesis Gemma-Swap Test Game

Investigation: 2026-07-30. Trigger: operator asked to trace the first two turns after the gemma/model-swap and explain "why the feature works on bedrock but does not work here".

## The Bug In One Line

`Pipe.getMiddlePromptForReasoning()` and `Pipe.getFooterPromptForReasoning()` cast a `pipeMetadata` lookup to non-null `Boolean` without first checking the key exists. When the reasoning pipe's metadata was never populated by `ReasoningBuilder.assignDefaults(...)`, the cast crashes with `NullPointerException: null cannot be cast to non-null type kotlin.Boolean` at line 8033 / 8047.

## The Stack Trace (verbatim, two events, identical frames)

```
java.lang.NullPointerException: null cannot be cast to non-null type kotlin.Boolean
    at com.TTT.Pipe.Pipe.getMiddlePromptForReasoning(Pipe.kt:8033)
    at com.TTT.Pipe.Pipe.executeReasoningPipe(Pipe.kt:7201)
    at com.TTT.Pipe.Pipe.access$executeReasoningPipe(Pipe.kt:760)
    at com.TTT.Pipe.Pipe$executeMultimodal$2.invokeSuspend(Pipe.kt:6496)
    at kotlin.coroutines.jvm.internal.BaseContinuationImpl.resumeWith(ContinuationImpl.kt:34)
    at kotlinx.coroutines.DispatchedTask.run(DispatchedTask.kt:100)
```

## The Offending Source (TPipe branch `fix-streaming` @ 23903146, lines 8030-8050)

```kotlin
/**
 * Getter function to retrieve the middle prompt instructions from a pipe if the pipe's reasoning settings
 * were defined. Called on the parent pipe and attempts to poll the reasoning pipe to determine if it has
 * been set to use the middle prompt or not. If true, this parent pipe's middle prompt will be returned.
 * Otherwise, returns an empty string.
 */
fun getMiddlePromptForReasoning() : String
{
    if(reasoningPipe == null) return ""
    val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as Boolean   // ← line 8033, unguarded
    if(!usingMiddlePrompt) return ""
    return middlePromptInstructions
}

fun getFooterPromptForReasoning() : String
{
    if(reasoningPipe == null) return ""
    val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as Boolean     // ← line 8047, unguarded
    if(!usingFooterPrompt) return ""
    return footerPrompt
}
```

## The Guarded Pattern That Was Used 200 Lines Earlier (lines 7166-7168 and 7208-7210)

```kotlin
if(reasoningPipe?.pipeMetadata["reinforceSystemPrompt"] is Boolean)
{
    val reinforceSystemPrompt = reasoningPipe?.pipeMetadata["reinforceSystemPrompt"] as Boolean
    if(reinforceSystemPrompt) { ... }
}
```

The same author wrote the surrounding code with `is Boolean` guards on every Boolean metadata read. Lines 8033 and 8047 are the only two unguarded `as Boolean` casts in the file. The bug is an inconsistency in the codebase, not a new class of mistake.

## The Eight Metadata Keys That `assignDefaults` Writes (ReasoningBuilder.kt:307-319)

```kotlin
targetPipe.pipeMetadata["reasoningRounds"]       = settings.numberOfRounds
targetPipe.pipeMetadata["focusPoints"]           = settings.focusPoints
targetPipe.pipeMetadata["roundDirectives"]       = settings.roundDirectives
targetPipe.pipeMetadata["injectionMethod"]       = settings.reasoningInjector.toString()
targetPipe.pipeMetadata["reasoningMethod"]       = settings.reasoningMethod.toString()
targetPipe.pipeMetadata["injectMiddlePrompt"]    = settings.injectMiddlePrompt   // Boolean, defaults to false
targetPipe.pipeMetadata["injectFooterPrompt"]    = settings.injectFooterPrompt   // Boolean, defaults to false
targetPipe.pipeMetadata["reinforceSystemPrompt"] = settings.reinforceSystemPrompt // Boolean, defaults to false
```

The first five are strings / collections (readers tolerate null). The last three are Boolean — **the only three Boolean metadata reads on `reasoningPipe.pipeMetadata`**. Removing or skipping `assignDefaults` leaves them absent, and the three read sites become trapdoors.

## Where The Bug Actually Lives (Autogenesis-side, not TPipe-side)

The four `ReasoningBuilder.reasonWith<Provider>` factories all route through `assignDefaults`. The bug is in autogenesis's `BedrockConfig.kt` Mantle builders, which construct reasoning pipes directly without `assignDefaults`:

### `buildMantleAuthorPipe` (BedrockConfig.kt:1116-1199)

```kotlin
private fun buildMantleAuthorPipe(...): Pipe {
    val pipe = GenericOpenAIPipe()
        .setBedrockMantle(region, modelId)
        .setPipeName(pipeName)
        .setMaxTokens(maxTokens)
        .setTemperature(temperature)
        .setTopP(topP)
        .setSystemPrompt(author)
        .setTokenBudget(...)

    pipe.apply {
        setTransformationFunction { pipeContent -> ... }
    }

    if (useFlex) { Logger.warn(...) }

    runBlocking { pipe.init() }

    pipe.pipeMetadata["showThinking"] = showThinking        // ← writes 4 metadata keys
    pipe.pipeMetadata["actorName"]   = actorName            // ← but none of the 3 reasoning-state
    pipe.pipeMetadata["isPlayer"]    = isPlayer             // ← Boolean flags from assignDefaults
    pipe.pipeMetadata["playerId"]    = playerId

    return pipe
}
```

### `buildMantleReasoningPipe` (BedrockConfig.kt:1313-1350)

```kotlin
private fun buildMantleReasoningPipe(...): Pipe {
    return GenericOpenAIPipe()
        .setBedrockMantle(region, modelId)
        .setPipeName(pipeName)
        .setMaxTokens(maxTokens)
        .setTemperature(temperature)
        .setTopP(topP)
        .setTokenBudget(...)
        .also { runBlocking { it.init() } }
}
```

**Neither writes any metadata.** Both bypass `assignDefaults` entirely.

## Why Bedrock Doesn't Hit It

`ReasoningBuilder.reasonWithBedrock(config, settings, pipeSettings)` always calls `assignDefaults` (ReasoningBuilder.kt:350). So does `reasonWithOllama` (line 373), `reasonWithOpenRouter` (line 400), and `reasonWithGenericOpenAI` (line 425). All four siblings are safe by construction. The Mantle builders in autogenesis sidestep the family and become the lone failure path.

## The Trace Surface — Round 1 Turn 0 `mantle validator pipe`

From `~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/ValidationSplitter/1785447941024/validator/trace.json`:

| Event | Type | Pipe | Model | Note |
|---|---|---|---|---|
| #100 | PIPE_START | mantle validator pipe | gemma-4-e2b | reasoningPipe set |
| #101 | CONTEXT_PREPARED | mantle validator pipe | gemma-4-e2b | actualInputTokens=3403 |
| #102 | **PIPE_FAILURE** | mantle validator pipe | gemma-4-e2b | NPE at Pipe.kt:8033 |
| #103 | API_CALL_START | mantle validator pipe | gemma-4-e2b | retry 1 |
| #104 | API_CALL_START | mantle validator pipe | gemma-4-e2b | retry 2 |
| #105 | API_CALL_START | mantle validator pipe | gemma-4-e2b | retry 3 |
| #106 | API_CALL_SUCCESS | mantle validator pipe | gemma-4-e2b | respLen=156, `{"isValid": true, ...}` |
| #107 | POST_GENERATE | mantle validator pipe | gemma-4-e2b | — |
| #108 | API_CALL_SUCCESS | (duplicate emission) | — | standard_pipeline emits twice |
| #109 | VALIDATION_START | mantle validator pipe | gemma-4-e2b | — |
| #110 | VALIDATION_SUCCESS | mantle validator pipe | gemma-4-e2b | **passed** |
| #111 | PIPE_SUCCESS | mantle validator pipe | gemma-4-e2b | — |
| #112-114 | downstream | style reapply pipe | qwen-coder-30b | ran cleanly |

The retry path's successful response (event #106) lacks the reasoning-pipe middle-prompt injection. The validator's small prompt degrades gracefully — it still knows the schema from the system prompt alone and emits `{"isValid": true, "assessment": "..."}`. The branch did not fail; three API calls' worth of latency was spent recovering.

## The Cascading Failure — `Play Detection Agent`

Same NPE, same fix-on-retry, but the retry response carries an empty schema:

```
Event #7  API_CALL_SUCCESS  respLen=59  text='{}'
Event #9  API_CALL_SUCCESS  respLen=None  text='{}'
Event #12 PIPE_SUCCESS      text='{}'
```

Expected schema (per `identifyPlayAgent.kt:31-35`):

```kotlin
@Serializable
data class PlayTypeObj(
    var type: PlayType = PlayType.Military,            // Military|Diplomatic|Research|Summit
    var doesPlayerHaveEnoughPoints: Boolean = true
)
```

The transformation function `extractJson<PlayTypeObj>(content.text)` (line 160-164) returns null because no `type` field exists, the transformation logs `"IdentifyPlay: identifyPipe.setTransformationFunction failed: result is null"`, and returns `content` unchanged. Downstream classification code that branches on `type` sees the broken `{}` and cannot pick a play type for either turn.

Cross-turn confirmation: identical `{}` payload on Round 1 Turn 1 (Robert), proving this is a property of the reasoning-pipe / model pair, not a turn-specific anomaly.

## The Fix Paths (Two Valid Options)

### Option 1 — Pipe.kt (the surgical two-line fix)

Replace the unguarded casts at lines 8033 and 8047:

```kotlin
// Before:
val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as Boolean
val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as Boolean

// After:
val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as? Boolean ?: false
val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as? Boolean ?: false
```

`false` matches the `assignDefaults` default (`ReasoningSettings.kt:151-152`), and `as? Boolean` is consistent with the `is Boolean` guard pattern used at lines 7166 and 7208.

**Pros:** Two lines. Independent of which reasoning-pipe factories exist now or later. Catches future regressions in any consumer of `getMiddlePromptForReasoning`.

**Cons:** Doesn't fix the upstream factory gap — other `injectMiddlePrompt`-shape consumers (if any are added later) still miss the metadata.

### Option 2 — Factory-side: route Mantle builders through `assignDefaults`

Update `BedrockConfig.buildMantleAuthorPipe` and `BedrockConfig.buildMantleReasoningPipe` to call `ReasoningBuilder.assignDefaults(reasoningSettings, pipeSettings, pipe)` before returning. Add a default `ReasoningSettings(...)` instance for the Mantle case (depth/duration come in as parameters; the rest can use the defaults).

**Pros:** Mantle becomes a first-class reasoning-provider citizen. All `pipeMetadata` keys populated. No future regression on this bug class.

**Cons:** Larger change. The Mantle wire carries its own non-standard reasoning payload that `assignDefaults` may not shape correctly — testing required. The author's transformation function on `buildMantleAuthorPipe` may interact with the JSON output class that `assignDefaults` sets via `requireJsonPromptInjection()`.

## Recommended Order

1. **Ship Option 1 (Pipe.kt) first.** It's the inconsistency-with-surrounding-code fix and removes the trapdoor for any future reasoning-pipe factory that bypasses `assignDefaults`.
2. **Then ship Option 2 (Mantle → assignDefaults) as a separate PR.** This makes Mantle reasoning pipes indistinguishable from Bedrock reasoning pipes at the parent-pipe boundary.
3. **Verification after Option 1 lands.** Run `python3 scripts/verify_extraction.py --strict` for the new state, plus a live test with the autogenesis gemma-swap turn-0 trace. Confirm: zero `PIPE_FAILURE` events with the NPE signature, `mantle validator pipe` shows 1 API_CALL_START (no retries), `Play Detection Agent` returns a non-empty schema. Total event count for the turn should drop by the four NPE recovery loops.

## Reproduction Recipe (Detection)

```bash
python3 -c "
import json, os, sys
needle = 'null cannot be cast to non-null type kotlin.Boolean'
hits = []
for root, _, files in os.walk(sys.argv[1]):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        for ev in json.load(open(os.path.join(root, f))):
            md = ev.get('metadata') or {}
            if needle in (md.get('error') or ''):
                hits.append((ev.get('pipeName'), md.get('model'), md.get('pipeClass')))
for h in hits[:20]:
    print(h)
" /path/to/trace/dir
```

Hit signatures in this incident:
- `mantle validator pipe` + `google.gemma-4-e2b` + `genericOpenAIPipe.GenericOpenAIPipe`
- `Play Detection Agent` + `google.gemma-4-e2b` + `genericOpenAIPipe.GenericOpenAIPipe`

Both trace back to Mantle-side reasoning-pipe factories bypassing `assignDefaults`.

## Trace Inventory (for any future "is this still broken?" check)

| Turn | Directory | PIPE_FAILURE count (NPE signature) | Mantle pipe affected |
|---|---|---|---|
| Round 1 Turn 0 (Lord Maple Tree) | `~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/` | 2 | `mantle validator pipe`, `Play Detection Agent` |
| Round 1 Turn 1 (Robert) | `~/.tpipe/debug/trace/Round_1_Turn_1_Robert/` | ≥1 | `Play Detection Agent` (validator cleaner on T1) |

After the Option 1 fix, both directories should show PIPE_FAILURE count = 0 for this NPE signature, Mantle reasoning pipes should show exactly one API_CALL_START per pipe run, and `Play Detection Agent` should return a populated `PlayTypeObj` JSON.
