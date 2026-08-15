# Strategic-Pipe In-Flight Stall with Token-Delta Duplication Runaway

Real session: 2026-08-02 13:37–13:48 UTC, Round 4 Turn 1 (Robert), namespace `echoofmaridia-autogenesis`.
**Discovered via server log + browser log, NOT TPipe trace artifacts** — the trace directory was cleared at boot (`AUTOGENESIS_DEBUG_TRACE=false`, server log L5) and no trace files were written for this turn.

## What the User Reported

The Agent Work Stream window in the KVision browser client produced text containing visible **token/subword duplication**:

> `II must must balance balance ...`
> `ApplyingApplying structural structural ...`

The text kept streaming, never completed, and the turn never resolved. The user forced a disconnect after ~10 minutes of waiting.

## Distinct From Existing Pitfalls

This is **NOT** the same failure as Pitfall 7 (Mantle NPE cascade at `Pipe.kt:8033` producing empty `{}`) or Pitfall 8 (`territoryExchanges` schema-vs-orchestration mismatch). Both of those produce **early-exit errors** (PIPE_FAILURE / API_CALL_FAILURE events). The 2026-08-02 stall is different:

| Pitfall 7 (NPE cascade) | Pitfall 8 (schema mismatch) | **2026-08-02 stall** |
|---|---|---|
| Pipe throws, exits early with empty result | Pipe exits with malformed JSON, downstream rejects | Pipe LLM call **never completes**; stream emitter enters runaway loop broadcasting duplicated deltas |
| `PIPE_FAILURE` + `API_CALL_FAILURE` events present | `VALIDATION_FAILURE` events present | **No failure events**, no completion, just continuous `isComplete=false` chunks |
| Trace shows clear error | Trace shows schema-rejection path | Trace would show... nothing beyond `setTransformationFunction`/`setPreValidationMiniBankFunction` calls (which is what we observed in the server log) |

The 2026-08-02 failure leaves no TPipe trace breadcrumbs — the streaming emitter is the only visible signal, and the browser log is the only place where the failure mode is observable. **If `AUTOGENESIS_DEBUG_TRACE` is OFF (the default), only the server log + browser log preserve the failure.**

## The Three-Stage PlayerAgent Pipeline

Built at `TurnHarness.handleAiTakeover` → `PlayerAgent: Building pipeline for Robert [analysis -> strategic -> execution]` (server log L250). Three sequential pipes:

1. **`analysisPipe`** — initial reasoning over the snapshot, world state, commander's history
2. **`strategicPlanningPipe`** — strategic decision (build/manipulate/conquer/etc.)
3. **`executionPipe`** — produces the final action

Each pipe has `setPreValidationMiniBankFunction` (initialized first) and `setTransformationFunction` (initialized last, before pipe body runs).

## The Stall Timeline (server log: `autogenesis-2026-08-02-093722.log`)

```
13:37:22.502  Server boot, AWS Bedrock creds loaded (L1-25)
13:37:46.060  TurnHarness.executeSingleTurn → handleAiTakeover for Robert (L235)
13:37:46.370  PlayerAgent: Building pipeline for Robert [analysis -> strategic -> execution] (L250)
13:37:46.510  [ERROR] Failed to initialize Bedrock inference config:
                bedrock.local.properties missing key 'bedrock.llamaScout17B' (L254)
              ← pre-pipe Bedrock Mantle/fallback config error
13:37:47.488  analysisPipe.setPreValidationMiniBankFunction entry (L277)
13:37:47.496  analysisPipe.setPreValidationMiniBankFunction success (L278)
13:37:58.667  Client subscribes to game.agentWorkStream.subscribe (L281)
13:38:04.063  [THINKING_CAPTURE] Broadcasting for Robert — analysis streaming (L283)
13:38:11.180  analysisPipe.setTransformationFunction entry (L287)
13:38:11.182  analysisPipe.setTransformationFunction success (L288)   ← ANALYSIS PIPE COMPLETE
13:38:11.213  strategicPlanningPipe.setPreValidationMiniBankFunction entry (L289)
13:38:11.219  delegate_guidance injected, rawPlayerLength=0 blockLength=92 (L292)
13:38:11.219  strategicPlanningPipe.setPreValidationMiniBankFunction success (L293)
            ┌──────────────────────────────────────────────────────────────────────┐
            │  13:38:11.219 → 13:42:46.056 : 4m 35s of NO PIPELINE ACTIVITY       │
            │  No LLM request log line, no completion event, no error, no timeout │
            └──────────────────────────────────────────────────────────────────────┘
13:42:46.056  TurnHarness.scheduleMusicRerollFallback fires (mid-turn music reroll, L294)
13:43:41.857  Second WebSocket arrives (server-extend-resume-push, CONTROLLER)
              — only restoreStatus + client.resumeAvailable, NO AI restart (L304-336)
13:47:46.058  TurnHarness.scheduleMusicRerollFallback fires again (L338)
13:48:35.639  Server: Stopping gRPC/grpc-web bridge (L348)
13:48:35.649  Client kvision-ws-client-561177945 disconnects; save-on-disconnect SKIPPED (L357-358)
13:48:35.649  "No PRIMARY sessions remain ... 60-second shutdown timer" (L359)
13:48:36.285–13:48:37.535  [WARN] Cannot send agent work stream, session not found (L360-365)
              ← server STILL EMITTING stream chunks for ~1.5s post-disconnect
13:48:37.653  GrpcServer: Shutdown complete (L366)
```

## The Stall Timeline (browser log: `browser-2026-08-02-093728.log`)

```
13:37:28.250  Boot (L1)
13:37:46.052  UiSignalClientHandlers: Set Local Player = Lord Maple Tree (L373)
13:37:46.195  Active turn actor=Robert (local=false) round=4 index=1 (L413)
13:37:54.571  First stream chunk arrives but DROPPED — AgentWorkStream window not visible (L2585)
13:37:58.664  AgentWorkStreamManager.openStream → Window shown and focused (L2659)
13:37:58.825  Streaming activated (storedChars=271) — first VISIBLE chunk (L2663)
13:37:58 → 13:38:11.336   ~60 normal chunks (100–500 char), 250ms cadence
                        ← analysis-pipe thinking/text streaming
13:38:11.336 → 13:38:33.603   *** 22-SECOND SILENCE ***
                              Server transitioning analysis → strategic pipe
13:38:33.603  Stream resumes, contentLen=2 (pipe boundary marker) (L2790)
13:38:33 → 13:39:04   small chunks resume (~150–300 char) — strategic pipe emitting
13:39:04.884 → 13:39:18.897   *** TOKEN/SUBWORD DUPLICATION ANOMALY ***
                              chunk sizes: 500, 1240, 1240, 248, 496, 1488, 744, 496,
                                           1240, 1736, 1488, 186, 310, 2232, 992,
                                           1488, 1488, 1240, 744, 992, 1240, 2976,
                                           1240, 496, 1488, 248, 992, 1488, 1488,
                                           2976, 1488, 1488, 1240, 248, 248, 992,
                                           1240, 2728, 1240, 248, 992, 2728, 1488,
                                           1240, 496, 496, 496, 1240, 1240, 1984
                              All values are exact multiples of 248:
                                248×1, 248×2, 248×3, 248×4, 248×5, 248×6,
                                248×8, 248×9, 248×11, 248×12
13:39:23 → 13:40:04    thinned out — only 248-byte chunks every few seconds
13:40:10 → 13:48:34.034  stream continues with 248/496/744-byte deltas at 250ms cadence,
                         NEVER emits isComplete=true (1728 chunks total, isComplete=true count = 0)
13:48:34.034   *** LAST ENTRY *** isComplete=false — browser log truncated mid-write (L6911)
```

## The Chunk-Size Fan-Out Math

After the 22-second inter-pipe silence, the stream resumed and the streaming emitter began broadcasting **248-byte delta chunks at 250ms cadence** (the standard cadence for the pipeline). But then it entered a runaway pattern where the **same 248-byte delta was broadcast N times per tick** before advancing to the next delta:

- Peak observed fan-out: **12×** (contentLen=2976 at 13:39:10.888)
- Typical fan-out during anomaly: 2×–8×

This produces the visible "II must must balance balance" / "ApplyingApplying structural structural" pattern: the underlying LLM may have emitted "must balance" once, but the streaming emitter broadcasts the same string 2× or 8× as separate chunks, which the renderer concatenates into the user's visible duplication.

The fan-out eventually decays to 1× (only 248-byte chunks, one per tick) by ~13:40:10, but the **stream never completes** — `isComplete=true` is never emitted across all 1728 chunks.

## Why This Stall Is Hard To Detect From TPipe Traces Alone

When `AUTOGENESIS_DEBUG_TRACE=false` (the default), no per-pipe trace files are written. The TPipe trace directory is cleared at boot (server log L5: `Trace directory cleared (1 entries)`). The only signals available are:

1. **Server log line `PlayerAgent: analysisPipe.setTransformationFunction success`** — confirms the analysis pipe completed but the strategic pipe never produced its equivalent log line
2. **Browser log `AgentWorkStreamManager.handleStream ... isComplete=false`** — the stream emits but never signals completion
3. **`AUTOGENESIS_DEBUG_TRACE=true`** would have produced a per-pipe trace directory; absence of `strategicPlanningPipe` traces beyond initialization confirms the pipe never ran an LLM call

If you see `setPreValidationMiniBankFunction` + `setTransformationFunction` entries for `analysisPipe` but no equivalent trace events for `strategicPlanningPipe`, the strategic pipe is **stuck in initialization or stalled before its LLM call began**. The 4m 35s silence on a single-player turn is the smoking gun.

## Pre-Pipe Bedrock Config Error (Likely Root Cause)

Server log L254:
```
13:37:46.510 [ERROR] [SYSTEM]: Failed to initialize Bedrock inference config:
  bedrock.local.properties missing key 'bedrock.llamaScout17B'
  (file: /home/cage/.autogenesis/config/bedrock.properties)
```

The Mantle / Bedrock fallback inference client (`bedrock.llamaScout17B`) failed to initialize at pipeline-build time. The error is logged once but not retried. The strategic pipe then enters its LLM call against an uninitialized (or stub) inference client, which:

1. Returns a degenerating stream of partial responses (the 248-byte deltas observed in the browser log)
2. Never emits the completion signal that would satisfy `isComplete=true`
3. The streaming emitter happily broadcasts whatever deltas it receives, fanning out 1–12× per tick
4. The TurnHarness coroutine waits forever for `handleAiTakeover` to return; only `scheduleMusicRerollFallback` (cosmetic mid-turn music) keeps the session alive

The fan-out is consistent with a **streaming accumulator bug** where the emit callback is invoked N times for the same partial buffer per tick. But the underlying root cause is the broken Bedrock inference client.

**Recommended fix path:**

1. Add `bedrock.llamaScout17B=<model-id>` to `/home/cage/.autogenesis/config/bedrock.properties` (verify the exact model ID is provisioned in Bedrock)
2. Add a hard timeout to `PlayerAgent.handleAiTakeover` — if the AI takeover coroutine doesn't return within N seconds (suggest 60s for strategic pipe, 120s total), force-abort and emit a `TurnHarness.AI_TAKEOVER_TIMEOUT` event so the TurnHarness can advance the turn loop
3. Add a watchdog that detects when `AgentWorkStream` emits N consecutive `isComplete=false` chunks for the same pipe without a completion — auto-close the stream and mark the pipe as failed

## How To Reproduce The Diagnosis

```bash
# 1. Locate the logs
ls -la ~/.autogenesis/logs/ | grep "$(date +%Y-%m-%d)"

# 2. Find the analysis-pipe completion and the strategic-pipe stall
grep -n "PlayerAgent:" ~/.autogenesis/logs/autogenesis-$(date +%Y-%m-%d)-*.log | head -20

# 3. Count browser stream chunks and check completion
grep -c "isComplete=false" ~/.autogenesis/logs/browser-$(date +%Y-%m-%d)-*.log
grep -c "isComplete=true"  ~/.autogenesis/logs/browser-$(date +%Y-%m-%d)-*.log

# 4. Check for the Bedrock Mantle config error
grep "bedrock.llamaScout17B" ~/.autogenesis/logs/autogenesis-$(date +%Y-%m-%d)-*.log

# 5. Check for post-disconnect stream emissions (the smoking gun for runaway loop)
grep "Cannot send agent work stream" ~/.autogenesis/logs/autogenesis-$(date +%Y-%m-%d)-*.log
```

If `isComplete=true` count is 0 AND `isComplete=false` count is > 500 AND `bedrock.llamaScout17B` config error is logged AND `Cannot send agent work stream` post-disconnect warnings appear, the diagnosis is "strategic-pipe in-flight stall with token-delta duplication runaway" caused by broken Bedrock inference client initialization.

## Cross-References

- **Existing pitfall 7** (Mantle NPE cascade at Pipe.kt:8033) — different mechanism (early-exit error vs. in-flight stall) but same Mantle family
- **Existing pitfall 8** (`territoryExchanges` schema mismatch) — different mechanism (schema rejection vs. no completion) but same post-Mantle-cutover era
- **Mantle model audit** — `autogenesis-agent-pipe-model-audit` skill, references the Bedrock config file
- **Browser log analysis** — `autogenesis-game-mechanics` or browser-side skills may have related patterns