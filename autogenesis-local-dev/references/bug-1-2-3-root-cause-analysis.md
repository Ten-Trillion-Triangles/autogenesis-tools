# Bug #1, #2, #3 — Root Cause Analysis (2026-05-22)

Confirmed from ~435 log files + 7 trace directories. User's own analysis used.

---

## Bug #1: JSON Failures During Judgement

**Severity:** HIGH | **Confidence:** 100%

### Log Evidence
```
02:32:47 [ERROR] [SYSTEM]: Failed to extract prior LLM result in legality rectifier pipe
02:52:25 [ERROR] [SYSTEM]: Failed to extract prior LLM result in legality rectifier pipe
14:15:08 [ERROR] [SYSTEM]: Failed to extract prior LLM result in NPC legality rectifier pipe
```
Also evidenced by `(Planning...)` placeholder in `turnResult` + `turnStory: ""` with `wasPlayerSuccessful: false`.

### Root Cause

**validator.kt:603** — `preInvokeFunction`:
```kotlin
val priorLlmResult = extractJson<`Legal?`>(it.text)
if(priorLlmResult == null) {
    it.terminate()   // KILLS pipeline immediately, no retry, no fallback
    return@setPreInvokeFunction false
}
```

**validator.kt:658-663** — `transformationFunction`:
```kotlin
val result = extractJson<`Legal?`>(it.text)
if(result == null) {
    return@setTransformationFunction it  // silently returns broken text unchanged
}
```

Same pattern in `npcValidationAgent.kt:171-177`.

### Fix Direction

- Add retry: on `extractJson` failure, strip markdown/code block wrappers and retry before terminating
- `preInvokeFunction` should attempt repair before calling `terminate()`
- Keep the original text instead of terminate() so the turn proceeds with degraded fidelity

### Files to Change
- `server/src/main/kotlin/agent/builders/validateAction/validator.kt` — lines ~600-610, ~656-669
- `server/src/main/kotlin/agent/builders/validateAction/npcValidationAgent.kt` — lines ~171-177

---

## Bug #2: Thinking Vanishes After Turn (thinkingUpdates: [])

**Severity:** HIGH | **Confidence:** 100%

### Log Evidence
```
thinkingUpdates: [] appears in multiple completed turn payloads (lines 974, 2201, 3535, 9172, 10935)
[WARN] [THINKING_CAPTURE] Reasoning response is default - skipping broadcast.
```

Two failure modes: (1) `showThinking=false` — pipe configured to skip capture; (2) `isDefault=true` — JSON parsing failed.

### Root Cause — Two Parallel Pipelines Not Connected

**Pipeline A — Real-time broadcast (WORKS):**
```
BedrockConfig.kt:595-636 (explicitCotBuilder transformationFunction)
    ↓
extractJson<MethodActorResponse>(pipeContent.text)  // line 599
    ↓
reasoningResponse.isDefault() check (line 601) → skip if true
    ↓
UiSignalRpcHandlers.broadcastThinking(thinkingData)  // line 626
    ↓
"ui.thinkingUpdate" WebSocket notification → browser receives thinking in real-time ✓
```

Confirmed working: `[THINKING_CAPTURE] Broadcasting thinking update for character=Robert`.

**Pipeline B — Persistent storage (BROKEN):**
```
GameHistory.kt:98 — var thinkingUpdates: MutableList<ThinkingUpdateData> = mutableListOf()
    ↓
[Nothing ever writes to it]
```

Zero `thinkingUpdates.add(...)` references in entire codebase. The field is dead code.

### User Requirement (NON-NEGOTIABLE)

> "it arrives. IT FUCKING STAYS THERE AND DOESN'T GET DELETED, THEN THE NEXT EVENT FROM THE TURN ARRIVES, AND APPENDS TO THE HISTORY. THIS ISN'T HARD."

Thinking must be written into history at the moment it arrives. Order of arrival must be preserved. Nothing is ever deleted.

### Fix — Direct Append at Moment of Arrival

```
Thinking arrives at BedrockConfig.kt:626
    ↓
UiSignalRpcHandlers.broadcastThinking(thinkingData)  → real-time to client ✓
    ↓
WorldManager.appendThinkingToHistory(turnId, thinkingData)  → persisted immediately ✓
```

**Implementation:**

1. **WorldManager.kt** — add thread-safe append:
```kotlin
fun appendThinkingToHistory(turnId: String, thinking: ThinkingUpdateData) {
    worldMutex.withLock {
        history.find { it.id == turnId }?.thinkingUpdates?.add(thinking)
        stagedHistoryEntries[turnId]?.thinkingUpdates?.add(thinking)
    }
}
```

2. **BedrockConfig.kt:626** — after broadcast, immediately:
```kotlin
runBlocking {
    UiSignalRpcHandlers.broadcastThinking(thinkingData)
    WorldManager.appendThinkingToHistory(turnId, thinkingData)
}
```

3. **Orchestrators** — set current turnId before pipes so the capture callback can read it:
   - gameplayOrchestrator:617 and npcOrchestrator:371 — call `BedrockConfig.setCurrentTurnId(turnId)` before pipes
   - BedrockConfig stores it for the transformationFunction callback

**Critical constraint:** `thinkingUpdates` on GameHistory must NEVER be cleared, reset, or overwritten. Only `.add()` is allowed. This guarantees FIFO order.

### Files to Change
- `server/src/main/kotlin/gameState/WorldManager.kt` — add `appendThinkingToHistory(turnId, thinkingData)`
- `server/src/main/kotlin/globals/BedrockConfig.kt` — lines ~595-636 (add WorldManager append after broadcast)
- `server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt` — set current turnId before pipes
- `server/src/main/kotlin/agent/runners/npcOrchestrator.kt` — set current turnId before pipes

---

## Bug #3: NPC Thinking Not Fully Captured as Expected

**Severity:** MEDIUM | **Confidence:** 95%

Same two-pipeline disconnect as Bug #2. NPC pipes set `showThinking=true`, the broadcast fires, but `GameHistory.thinkingUpdates` is never populated.

Additionally suspect: **thinking may live in the reasoning pipe sub-agent's output, not the author pipe.** `pipeContent.text` at line 599 is the parent pipe's text, not necessarily the reasoning sub-agent's output. If the reasoning sub-agent writes to a different field, `extractJson` reads the wrong text and returns `isDefault`.

### Fix Direction

Same as Bug #2 — connect the two systems with direct append.

Also verify `MethodActorResponse` schema matches the actual JSON output of the reasoning sub-agent for NPC pipes.

### Files to Change
Same as Bug #2. Also verify:
- `server/src/main/kotlin/agent/builders/gameplayActions/npcActorAgent.kt` — reasoning pipe config
- `server/src/main/kotlin/agent/builders/gameplayActions/npcHostileAgent.kt` — reasoning pipe config
- `BedrockConfig.kt:599` — what `pipeContent.text` actually contains for NPC pipes