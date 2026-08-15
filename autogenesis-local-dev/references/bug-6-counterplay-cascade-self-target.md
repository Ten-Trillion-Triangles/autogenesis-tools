# Bug #6 — Counterplay Cascade Self-Targeting (Root Cause + Fix)

**Session:** 2026-05-22  
**Severity:** HIGH  
**Status:** Root cause identified, fix pending application

---

## The Bug

A player who targets themselves with a hostile action can trigger cascade counter-responses against OTHER players. The cascade system has no guard preventing a player from being added as their own cascade target.

Example from session: Lord Maple Tree's counter-response included targeting Ghor'lax in cascade — a valid chain, but the self-target gap was confirmed as the underlying vulnerability.

---

## Root Cause — Cascade Detection Gap (gameplayOrchestrator.kt:1547-1568)

The cascade loop processes each defender's counter-response and detects new targets. Cycle detection exists:

```kotlin
if(targetPlayer.name == responseData.respondingTo.name) {
    // CYCLE: A → B → A — blocked
    Logger.warn("[CASCADE] CYCLE DETECTED: ...")
} else if(targetingChain.contains(newTargetingKey)) {
    // DUPLICATE: A → B → B — blocked
    Logger.warn("[CASCADE] DUPLICATE targeting detected: ...")
} else {
    newTargets.add(targetPlayer)  // ← B can be added here if B targets B
}
```

**The gap:** No check for `targetPlayer == responseData.player` (self-target). A player whose counter-response mentions themselves as a target bypasses both guards:
- `targetPlayer == respondingTo` → FALSE (B is not the original attacker)
- `targetingChain.contains("B→B")` → FALSE (B→B was never added)

So B gets added to `newTargets` and enters the next cascade depth, triggering counter-responses from players who shouldn't be involved.

---

## The Initial Target Guard vs Cascade Guard Mismatch

Initial target resolution (lines 1359-1367) HAS the self-target guard:

```kotlin
if (!foundPlayer.name.equals(player.name, ignoreCase = true)) {
    initialTargets.add(foundPlayer)
}
```

But the cascade loop (lines 1547-1568) does NOT have the equivalent. The fix closes this gap.

---

## Fix (pending application)

Add a self-target check at gameplayOrchestrator.kt:1555-1560, inside the cascade target resolution block:

```kotlin
val newTargetingKey = "${responseData.player.name}→${targetPlayer.name}"
// Cycle detection: A -> B -> A
if(targetPlayer.name == responseData.respondingTo.name) {
    Logger.warn(LogCategory.GENERAL, "[CASCADE] CYCLE DETECTED: ...")
}
else if(targetPlayer.name.equals(responseData.player.name, ignoreCase = true)) {
    // SELF-TARGET: B targets B — block cascade for self-targeting
    Logger.warn(LogCategory.GENERAL, "[CASCADE] SELF-TARGET DETECTED: ${responseData.player.name} targets themselves in cascade. Skipping.")
}
else if(targetingChain.contains(newTargetingKey)) {
    Logger.warn(LogCategory.GENERAL, "[CASCADE] DUPLICATE targeting detected: ...")
}
else {
    newTargets.add(targetPlayer)
}
```

This mirrors the guard already in place at the initial target resolution stage.

---

## Why This Was Invisible

The real-time WebSocket broadcast works correctly — counter-responses fire and cascade fires for legitimate targets. The self-target case is rare (a player must explicitly target themselves in their counter-response text), so it doesn't surface in every game. The cycle detection (A→B→A) handles the obvious case, but the self-target gap is a separate logical path.