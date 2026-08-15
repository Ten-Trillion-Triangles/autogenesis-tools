# Bug #10 Fix: Judge Overrode StatVictory for Unowned Territory

**Date:** 2026-05-22  
**Bug:** Judge LLM denied territory capture despite `statVictory=true`, `finalSuccess=true`, and an unowned target.  
**Severity:** Core game mechanic violation — player won the math roll but was denied the reward.

## Root Cause Chain

1. **GameMath computed correctly:** `baseScore=20, earlyRoundBoost=80, totalScore=60, statVictory=true, finalSuccess=true`
2. **Pass/Fail pipe wrote SUCCESS** to `JUDGE_OUTCOME_CONTEXT` ✓
3. **Gains/Losses LLM received** "Turn Outcome: SUCCESS" but was overridden by narrative rules ("softened victory", "narrativeVictory=false")
4. **LLM output:** `territoryGained=[]` — the loophole
5. **`enforceMandatoryTerritoryCapture`** was gated by `!wasSuccessful` — didn't fire because narrative flip set `wasSuccessful` based on narrative outcome, not math outcome

**The vulnerability:** Narrative framing could flip `wasSuccessful` from `true` to `false`, which then disabled the one mechanical safeguard that could catch LLM output errors.

## Three-Layer Fix

### Layer 1 — Prompt (judge.kt gains/losses prompt, new STEP 5 rule)

```kotlin
/**STEP 5: UNOWNED TERRITORY AUTO-CAPTURE (CRITICAL - NEW RULE)**
   - If the target territory has NO OWNER (no ruler) at the start of resolution
   - AND the player scored statVictory=true (positive score, successful mathematical outcome)
   - AND no counterplay was possible (no defending forces, no NPC response triggered)
   - THEN the territory is AUTOMATICALLY captured by the player
   - This applies REGARDLESS of narrative framing, tone, or "softened victory" language
   - The player cannot be denied an unowned territory when they won the roll
*/
```

### Layer 2 — Mechanical (judge.kt rewritten `enforceMandatoryTerritoryCapture`)

Removed the `!wasSuccessful` gate for unowned territory. The rewritten function now:
1. Reads `math_outcome` from ContextBank to get `statVictory` directly
2. If `isUnowned && statVictory && territory not in territoryGained` → force-adds territory
3. Preserves normal path for owned territories

### Layer 3 — Reasoning Depth (BedrockConfig.kt)

Changed `explicitCotBuilder` default from `ReasoningDepth.Low` to `ReasoningDepth.High`. Every call site was already passing `ReasoningDepth.High` explicitly — the default was silently wrong and only respected when callers forgot to pass the parameter.

## Key Code Changes

| File | Change |
|------|--------|
| `server/src/main/kotlin/globals/BedrockConfig.kt:833` | `ReasoningDepth.Low` → `ReasoningDepth.High` default |
| `server/src/main/kotlin/agent/builders/judgeOutcome/judge.kt` | STEP 5 added to gains/losses prompt; `enforceMandatoryTerritoryCapture` rewritten |
| `server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt` | `math_outcome` stored in ContextBank after Phase 8 |

## How `math_outcome` Flows to `enforceMandatoryTerritoryCapture`

```
GameMath.resolveAction()          gameplayOrchestrator Phase 8        enforceMandatoryTerritoryCapture()
     │                                       │                                    │
     ├── MathOutcome(statVictory=true) ─── serialize() ─── ContextBank.emplace() ── ContextBank.get("math_outcome")
     │                                       │                                    │
     └─ stored as phase8_result ────────────┘                         └─ reads statVictory directly, bypasses LLM
```

## Lessons

1. **Never gate a mechanical safeguard on a value the LLM controls.** `wasSuccessful` was being flipped by the gains/losses LLM — using it to guard the enforcement function meant the LLM could disable its own oversight.
2. **Use ground-truth sources for mechanical checks.** `statVictory` from `MathOutcome` (the math layer) is authoritative; `wasSuccessful` from the LLM is not.
3. **Unowned territory is a special case.** An unowned territory has no defender, no counterplay, and no narrative reason to deny capture when the player wins the roll. The prompt must say this explicitly; the mechanical layer must enforce it regardless.
4. **Default parameter values matter.** The `ReasoningDepth.Low` default was silently overridden by every caller that mattered — meaning every important call was running at High despite the default saying Low. Wrong defaults are silent bugs.