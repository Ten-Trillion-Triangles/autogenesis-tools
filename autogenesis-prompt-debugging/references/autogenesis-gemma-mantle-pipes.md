# Gemma / Mantle reasoning pipe failure shapes (post-2026-07-30 gemma4-test branch)

Session-derived reference for the `tpipe-trace-parser` skill. Use this when inspecting autogenesis / Mantle-backed pipes for crashes, retry clusters, schema non-adherence, or downstream territory-state anomalies, especially when comparing Mantle output against a known-good Bedrock/Qwen reference pipe.

## Trigger conditions

Load this file when the trace triage uncovers any of:

- A `PIPE_FAILURE` event whose `metadata.error` contains `null cannot be cast to non-null type kotlin.Boolean`
- A `mantle validator pipe` / `mantle structured cot` / `mantle explicit cot` / `mantle process focused` event whose model field reads `google.gemma-4-e2b` or `google.gemma-4-31b` (NOT `arn:aws:bedrock:...`)
- A `Play Detection Agent` `API_CALL_SUCCESS` whose text is literally `{}`
- A `gains and losses pipe` output whose `territoryExchanges[*].to == ""`
- A user-reported "validator flyby" in the workstream window that does NOT show up as `BRANCH_FAILED`
- A user-reported "the judge awarded territory even though the defender repelled the attacker"

## Detection recipes

### Find every Gemma/Mantle reasoning pipe NPE

```python
import json, os
for root, _, files in os.walk('/home/cage/.tpipe/debug/trace/<dir>'):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        path = os.path.join(root, f)
        data = json.load(open(path))
        for i, ev in enumerate(data):
            if 'gemma' not in ((ev.get('metadata') or {}).get('model') or ''):
                continue
            err = (ev.get('metadata') or {}).get('error') or ''
            if 'cannot be cast to non-null type kotlin.Boolean' in err:
                stack = (ev.get('metadata') or {}).get('stackTrace') or ''
                print(path, i, ev.get('pipeName'),
                      stack.split('\n')[0] if stack else '')
```

The two call sites that throw this NPE (verified in TPipe source at branch `fix-streaming`, commit 23903146):

```
TPipe/src/main/kotlin/Pipe/Pipe.kt:8030-8036  fun getMiddlePromptForReasoning()
    val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as Boolean  // line 8033

TPipe/src/main/kotlin/Pipe/Pipe.kt:8044-8050  fun getFooterPromptForReasoning()
    val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as Boolean    // line 8047
```

Both read an absent metadata key as a non-null Boolean. Both are unguarded by the `is Boolean` check pattern used elsewhere in the same file at lines 7166-7168 and 7208-7210. Bedrock/Ollama/OpenRouter/`reasonWithGenericOpenAI` reasoning pipes write these keys via `ReasoningBuilder.assignDefaults` (`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:317-318`). The Mantle builders (`BedrockConfig.buildMantleReasoningPipe` at line 1313 and `BedrockConfig.buildMantleAuthorPipe` at line 1116 in the Autogenesis consumer-side repo) construct the pipe directly and never call `assignDefaults` — that is why Mantle reasoning pipes are the only ones that hit this NPE.

### Find every retry cluster on a Mantle reasoning pipe

The retry loop absorbs the NPE and re-runs `API_CALL_START` up to 3 times before the third attempt succeeds without the middle-prompt injection. Detect with a sliding window over consecutive events with the same `pipeName`:

```python
import json, os
for root, _, files in os.walk('/home/cage/.tpipe/debug/trace/<dir>'):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        path = os.path.join(root, f)
        data = json.load(open(path))
        for i in range(len(data) - 3):
            if all(
                data[i+j].get('eventType') == 'API_CALL_START'
                and data[i+j].get('pipeName') == data[i].get('pipeName')
                for j in range(3)
            ):
                print('RETRY CLUSTER:', path, 'event#', i, data[i].get('pipeName'))
```

A 3-attempt retry cluster on a Mantle pipe with no intervening `API_CALL_SUCCESS` is the signature of the NPE being absorbed. It does NOT mean the turn failed — the third attempt completes with reasoning-injection missing and the validator/branch downstream operates on the degraded reasoning.

### Find every `Play Detection Agent` empty `{}` response

```python
import json, os
for root, _, files in os.walk('/home/cage/.tpipe/debug/trace/<dir>'):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        path = os.path.join(root, f)
        data = json.load(open(path))
        for ev in data:
            if 'Play Detection' not in (ev.get('pipeName') or ''):
                continue
            if ev.get('eventType') != 'API_CALL_SUCCESS':
                continue
            text = (ev.get('content') or {}).get('text','')
            if text == '{}':
                print('EMPTY:', path, ev.get('metadata',{}).get('model'))
```

This is the post-NPE recovery response — Gemma-4-e2b, called without the middle-prompt reasoning injection, emits an empty JSON object that satisfies `requireJsonPromptInjection()` but fails the `PlayTypeObj` schema (`type: PlayType, doesPlayerHaveEnoughPoints: Boolean`). `extractJson<PlayTypeObj>(content.text)` returns null, the transformation function at `identifyPlayAgent.kt:160-164` logs `"result is null"` and returns `content` unchanged. Downstream code that branches on `type` (the 4-way play-type routing) sees no classification. This is consistent across both turns in a session — count occurrences to confirm the bug is on every turn, not just one.

### Find every `gains and losses pipe` territory exchange with empty `to`

```python
import json, os, re
for root, _, files in os.walk('/home/cage/.tpipe/debug/trace/<dir>'):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        path = os.path.join(root, f)
        data = json.load(open(path))
        for ev in data:
            if (ev.get('pipeName') or '') != 'gains and losses pipe':
                continue
            if ev.get('eventType') != 'API_CALL_SUCCESS':
                continue
            text = (ev.get('content') or {}).get('text','')
            for m in re.finditer(r'"to"\s*:\s*"([^"]*)"', text):
                if m.group(1) == '':
                    print('EMPTY to:', path, ev.get('metadata',{}).get('model'))
```

The judge prompt at `agent/builders/judgeOutcome/judge.kt:1042-1049` defines `to: ""` as "territory becomes neutral/contested". The orchestrator at `agent/runners/gameplayOrchestrator.kt:2285-2304` translates that to:

```kotlin
if(exchange.from.isNotBlank())  { outcome.territoriesLost.add(exchange.territoryName) }
if(exchange.to.isNotBlank())    { outcome.territoriesGained.add(exchange.territoryName) }
```

So `to: ""` strips the territory from the `from` holder and gives it to nobody — even when the narrative explicitly says the defender repelled the attacker. The `mantle validator pipe` (Gemma 4 E2B) that runs on this output accepts the empty `to` as a "valid intentional game logic for becoming neutral/contested" — that approval is itself a downstream effect of the Pipe.kt:8033 NPE (validator runs reasoning-less and approves whatever satisfies `requireJsonPromptInjection`). Qwen-coder-30b would still produce the same output (the schema permits `to: ""`), so this is a schema-level bug, not a Gemma-specific output bug.

### Find every Mantle validator approving an empty-string schema field

```python
import json, os
for root, _, files in os.walk('/home/cage/.tpipe/debug/trace/<dir>'):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        path = os.path.join(root, f)
        data = json.load(open(path))
        for ev in data:
            if ev.get('eventType') != 'VALIDATION_SUCCESS':
                continue
            if 'mantle validator' not in (ev.get('pipeName') or ''):
                continue
            text = (ev.get('content') or {}).get('text','')
            if 'isValid": true' in text and ('empty string' in text.lower() or 'neutral' in text.lower() or 'contested' in text.lower()):
                print('MANTLE VALIDATOR ACCEPTED EMPTY to:', path)
```

The Mantle validator's permissive-approval pattern is `isValid: true` with an assessment that explicitly cites "valid intentional game logic" / "neutral" / "contested" / "empty string". When this approval is on the `gains and losses pipe` output, the bug cascades into territory-state. When it is on any other validator pipe run, the same broken-reasoning acceptance is occurring but the downstream cost varies.

## Cross-references

- **Source defect:** `TPipe/src/main/kotlin/Pipe/Pipe.kt:8030-8036, 8044-8050` (TPipe branch `fix-streaming` at the time of detection — line numbers are stable across `fix-streaming`/`main` because both branches carry the same 8,223-line shape).
- **Mantle builder bypass site:** `BedrockConfig.buildMantleReasoningPipe` at `BedrockConfig.kt:1313-1350` and `BedrockConfig.buildMantleAuthorPipe` at `BedrockConfig.kt:1116-1199` (Autogenesis consumer-side repo).
- **Canonical metadata writer:** `TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:317-318`.
- **Guarded pattern reference (the model to follow):** `TPipe/src/main/kotlin/Pipe/Pipe.kt:7166-7168` and `Pipe.kt:7208-7210` (the `reinforceSystemPrompt` field uses `is Boolean` then `as Boolean`).
- **Territory-state cascade:** `agent/builders/judgeOutcome/judge.kt:1042-1049` (schema rule for `to: ""`) and `agent/runners/gameplayOrchestrator.kt:2285-2304` (orchestrator translation of `territoryExchanges` into `territoriesLost` / `territoriesGained`).
- **Operator handoff doc with full bug report + verification recipe:** `TPipe/BUG_INJECTMIDDLEPROMPT_GEMMA.md` (19 KB; intended for an agent that ships the fix).
- **Sibling trace-pattern reference:** `references/audio-injection-pattern.md`. The audio-injection pattern (world-snapshot serializer leaking the music catalog into every prompt, inflating per-turn input tokens ~2x) and the Mantle-NPE pattern (reasoning-pipe NPE silently retries, producing empty-JSON / schema-permissive outputs) are unrelated root causes that share the symptom of confusing per-call trace signal. Distinguish them by the failure-shape signature: audio-injection causes token-bucket inflation across all pipes uniformly; Mantle-NPE causes 3-attempt retry clusters and `{}` outputs on `Play Detection Agent` specifically.

## Verification shape (post-fix)

After applying the unguarded `as Boolean` → `as? Boolean ?: false` patch to `Pipe.kt:8033` and `Pipe.kt:8047`:

1. Re-run the live autogenesis test game on a Mantle-using branch.
2. Re-extract with `extract_pipeline.py --dir <new_trace_dir>` and confirm:
   - The NPE signature grep produces zero results (count: 0).
   - The 3-attempt retry cluster on any Mantle reasoning pipe produces zero results (count: 0).
   - The `Play Detection Agent` empty `{}` count is zero.
3. Run `python3 /home/cage/.hermes/skills/software-development/tpipe-trace-parser/scripts/verify_extraction.py --strict` and confirm `Ran 7 case(s); 0 failure(s)` exit 0.
4. If `mantle validator pipe` `isValid: true` assessment count drops (because reasoning injection is restored and the validator now rejects empty-`to` exchanges instead of accepting them), that is the expected and correct outcome.
