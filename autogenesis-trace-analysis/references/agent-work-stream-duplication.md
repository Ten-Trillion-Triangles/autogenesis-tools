# Agent Work Stream callback duplication (2026-08-02)

The Agent Work Stream window can show per-token doubling such as `II must must` or malformed JSON like `{{"is": "tr""is": "true"}}` even when the model returns clean output. Cause: the server-side work-stream factory and per-builder self-registration both attach forwarding callbacks to nested `GenericOpenAIPipe` reasoning pipes, and TPipe already propagates streaming callbacks to descendants — so a single provider delta is delivered to `AgentWorkStreamDispatcher.appendChunk` twice (or three times for the response refinement path).

This is a *callback wiring* bug, not a rendering bug. The UI appends each payload exactly once (`AgentWorkStreamWindow.appendChunk` → one `<p>` node). The doubling is already present in the chunk string when the WebSocket sends it.

## Affected pipes

Producer pipes that combine (a) a `GenericOpenAIPipe` host on Mantle with (b) a nested Mantle reasoning pipe via `setReasoningPipe`:

- **PlayerAgent strategic host** (`agent/builders/playerAgent/playerAgent.kt:126-142`) on `gemma31ModelId` with `mantleAuthorBuilder31B` reasoning. Wired into the work stream by `TurnHarness.generateAiAction` (`TurnHarness.kt:1020-1031`, `TurnHarness.handleAiTakeover` at `:1148-1159`), `gameplayOrchestrator.handleInitialSetupAndAiTakeover` (`:915-928`), and `gameplayOrchestrator.generateAiCounterResponse` (`:2822-2827`).
- **ResponseRefinementAgent** (`agent/builders/writingAgent/ResponseRefinementAgent.kt:37-199`). Two `GenericOpenAIPipe` entries (detect `:50-111`, refine `:113-193`), each with `setReasoningPipe`. Mantle streaming chat-completions deltas are token-by-token, so subword doubling is most visible here.

## How the three callbacks land on one pipe

For a generic host + nested generic reasoning pipe:

1. **Self-registration** (added in `ResponseRefinementAgent.kt:99-110` and `:181-192`, both introduced in commit `fd3f1c6a0` "attempt to unify streaming"). Attaches dispatcher callback A to the host's `streamingCallbackManager`. `GenericOpenAIPipe.streamingCallbacks` then runs `propagateStreamingCallback(callback)` (`TPipe-GenericOpenAI/.../GenericOpenAIPipe.kt:504-512` → `TPipe/.../Pipe.kt:1947-1970`), so A is also added to the reasoning pipe.
2. **Central factory walk** (`AgentWorkStreamStreaming.kt:68-69`). Loops `pipeline.getPipes()` (entry-level only — `TPipe/.../Pipeline.kt:780-786`) and calls `configureStreamingForPipes(...)` (`:82-92`).
3. **Factory explicit recursion into reasoning pipe** (`AgentWorkStreamStreaming.kt:107` — `configureStreamingForPipe(connectionIds, pipe.reasoningPipe, configured)`). For each entry-level pipe it adds a fresh lambda B to the reasoning pipe's manager.

A and B are different lambda objects → `StreamingCallbackManager.addCallback` does NOT dedupe (`TPipe/.../StreamingCallbackManager.kt:40-50` dedupes by reference equality). Each provider delta therefore triggers two appends on the reasoning pipe. For PlayerAgent the host also double-fires (its propagation puts A on host, factory B also on host). For ResponseRefinementAgent the same pattern triples: A (self) propagates to detect, refine, and both reasoning pipes; B (factory) additionally reaches detect+refine via `getPipes()`, and the factory's explicit recursion hits each reasoning pipe.

## Why this was not caught earlier

- `agent/runners/npcOrchestrator.kt:1477` calls `streamPipelineOutputToAgentWorkBuffer(recipientIds, refinementAgent)` *after* `buildResponseRefinementAgent(recipientIds)` — so by line 1500 the refinement agent already has its self-registered callbacks and the factory adds a second set on top.
- The factory's in-source comment claims "The consumer factory only walks Pipeline.getPipes() entry-level, so sibling pipes in the same pipeline aren't reachable from there" — that is exactly backwards. `Pipeline.getPipes()` (`TPipe/.../Pipeline.kt:780-786`) returns the entry-level list directly; the response refinement's two pipes ARE entry-level siblings. So the self-registration was added for a non-existent gap.
- `AgentWorkStreamStreamingTest.configureStreamingWiresCallbackOnGenericOpenAIPipe` (`server/src/test/.../AgentWorkStreamStreamingTest.kt:21-27`) only asserts presence (`getCallbacks().isNotEmpty()`), not uniqueness or count across descendants. No regression test exists for "exact one append per delta" through nested Mantle reasoning.
- `BedrockPipe.setStreamingCallback`/`addCallbackToDescendants` (`TPipe-Bedrock/.../BedrockPipe.kt:1022-1092`) deliberately uses a single-source-of-truth pattern (legacy field is canonical, descendants only get a copy to avoid double-fire via `emitStreamingChunk → streamingCallback + manager.emitToAll`). `GenericOpenAIPipe.streamingCallbacks` does NOT match that contract — `propagateStreamingCallback` adds the callback to `obtainStreamingCallbackManager().addCallback(...)` which then iterates the manager on emit. Caller-side dedupe at `StreamingCallbackManager.addCallback` compares references, so two distinct lambdas both survive.
- Mantle streaming amplifies the symptom because each `data: {"choices":[{"delta":{"content":"X"}}]}` line emits one chunk; Anthropic's `content_block_delta`/`input_json_delta` and Bedrock's `contentBlockDelta` are also per-token. Subword tokens (`"I"`, `" must"`) are most observable.

## Buffering does not mask the bug

`AgentWorkStreamDispatcher` itself is correct on a single-pipeline basis:

- One `StringBuilder` per connection (`AgentWorkStreamDispatcher.kt:29-35`).
- Synchronized append (`AgentWorkStreamDispatcher.kt:82-94`).
- Copy-and-clear on flush (`AgentWorkStreamDispatcher.kt:151-160`).
- One coroutine `launch` per flush (`AgentWorkStreamDispatcher.kt:168-177`).

So failures show up as doubled-but-ordered text within one ~250 ms flush window, not as reordered/merged fragments. That flush window is also where UI-window `appendChunk` builds a single `<p>` from the buffer's accumulated text (`AgentWorkStreamWindow.kt:106-129`).

## Fix direction

1. Pick exactly one of (a) work-stream-factory-only or (b) `ResponseRefinementAgent`-self-register-only — but not both. The factory is the right place because callers already drive the wiring; remove `streamingCallbacks` blocks inside `ResponseRefinementAgent.kt:99-110` and `:181-192`.
2. Drop the factory's explicit `pipe.reasoningPipe` recursion at `AgentWorkStreamStreaming.kt:107`. `GenericOpenAIPipe.streamingCallbacks` and `BedrockPipe.addCallbackToDescendants` already walk descendants. The factory's pipeline-level pass through entry-level pipes is sufficient.
3. Keep exactly one `pipelineCompletionCallBack` per pipeline. Currently the factory wraps it at `:71-79`; if callers also set one, the latest write wins and the prior callback is dropped (`Pipeline.kt:1182-1186`). Pass-through completion fans out to all recipients once.
4. Add a regression test asserting the dispatcher received exactly one append per model delta for: generic host + generic reasoning, generic host + bedrock reasoning, response refinement with `connectionIds` supplied, and PlayerAgent (`gemma31ModelId`) end-to-end.

## File:line evidence

- `server/src/main/kotlin/org/ttt/autogenesis/server/AgentWorkStreamStreaming.kt:82-92, 100-108, 132-146`
- `server/src/main/kotlin/agent/builders/writingAgent/ResponseRefinementAgent.kt:99-110, 181-192`
- `server/src/main/kotlin/agent/builders/playerAgent/playerAgent.kt:126-142`
- `server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt:915-931, 1608-1633, 2822-2835`
- `server/src/main/kotlin/agent/runners/npcOrchestrator.kt:1477-1489`
- `server/src/main/kotlin/agent/runners/SummitOrchestrator.kt:111-119`
- `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt:1020-1031, 1148-1159`
- TPipe `TPipe/src/main/kotlin/Pipe/Pipe.kt:1947-1970` (propagateStreamingCallback)
- TPipe `TPipe/src/main/kotlin/Pipe/StreamingCallbackManager.kt:40-50` (reference-equality dedupe — does not save us)
- TPipe `TPipe-GenericOpenAI/.../GenericOpenAIPipe.kt:466-475, 504-515` (setStreamingCallback + streamingCallbacks both call propagateStreamingCallback)
- TPipe `TPipe-Bedrock/.../BedrockPipe.kt:1012-1093` (Bedrock's contrasting single-source pattern — explains why Bedrock showed different symptoms historically)

## Diagnostic recipe (works without live network)

1. Stub `AgentWorkStreamDispatcher.appendChunkToMany` and wrap each append with `dispatcherCalls.append(connectionId to chunk)`.
2. Build `PlayerAgent` with a `gemma31ModelId` host pipe + a fake reasoning pipe that emits one known delta when its API is invoked.
3. Wire via both the factory AND a second copy mimicking `ResponseRefinementAgent`'s self-registration.
4. Assert `dispatcherCalls.count { it.second == delta }` is exactly 1 across all chunks for one provider call.

Production trace evidence: search for consecutive identical short strings in `~/.tpipe/debug/trace/.../AgentWorkStreamWindow` UI logs after a player turn — `LogCategory.UI "AgentWorkStreamWindow: Streaming data received ... chunkLength="` paired with two reads of the same string within a single flush window is the smoking gun.
