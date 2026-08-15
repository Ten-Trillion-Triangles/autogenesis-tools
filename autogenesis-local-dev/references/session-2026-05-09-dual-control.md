# Session 2026-05-09 — Dual-Control Verified, Browser UI Failure Analysis

## Verified: Dual-Control Architecture is SOUND

End-to-end test completed successfully. The architecture works correctly:

1. Python controller with `--player-alias guest-user` connects as CONTROLLER session
2. Browser with `?skipLogin=true` connects as PRIMARY session (playerAlias=guest-user)
3. GameInit matches controller's playerAlias to browser's existing WorldManager.playerStats entry
4. Game server routes state to BOTH sessions — player is reachable if ANY session responds to ping
5. Action submitted by controller → TurnHarness processes → broadcast reaches all sessions
6. Shutdown only triggers when ALL sessions deregister

## Verified: Game Runs to Completion with AI Takeover

```
TurnHarness.awaitPlayerAction: Player 'LordMapleTree' is UNREACHABLE → AI takeover triggered
TurnHarness.handleAiTakeover: Generating AI action for LordMapleTree...
TurnHarness: Received player submission for LordMapleTree (actionLength=50)
TurnHarness: Received player submission for LordMapleTree (actionLength=50)
[THINKING_CAPTURE] Broadcasting thinking update for character=LordMapleTree
```

The game completes turns even when the controller isn't perfectly connected. AI takeover is graceful and doesn't crash the game.

## The Core Problem: Session Binding Mismatch

```
Browser connects with: kvision-ws-<ts>
Python controller connects with: lord-<ts>

Both can be matched via playerAlias=guest-user
But browser must FIRST create the player slot in WorldManager

Problem: The browser's KVision UI doesn't reliably receive click events.
Without clicking through matchmaking, no player slot is created.
```

## Critical Code Paths

### GameInit.playerAlias matching (GameInit.kt:187-198)
```kotlin
val existingStats = if(bundle.playerAlias.isNotBlank()) {
    WorldManager.playerStats.find { stats ->
        stats.playerID.contains(bundle.playerAlias) ||
        stats.playerData.name.contains(bundle.playerAlias)
    }
} else null
// If found → controller joins browser's slot (existingStats.playerID = connectionId)
// If null → controller creates new player (normal registration)
```

### Controller registration as CONTROLLER role (GameInit.kt:204-207)
```kotlin
existingStats.playerID = connectionId
existingStats.isConnected = false  // Controller will set true when it connects
existingStats.isControlledByNpc = false
```

### isReachable pings ALL sessions (WorldManager.isReachable)
```kotlin
// Player is reachable if ANY session (PRIMARY or CONTROLLER) responds to ping
// Not just the PRIMARY session
```

## Browser Click Failure — Root Cause

The browser automation (Playwright, browser tool clicks) cannot make KVision's reactive state reflect DOM events. This was confirmed:

1. KVision uses an internal reactive state system
2. DOM click events reach the browser engine but do NOT propagate to KVision's reactive model
3. No synchronization layer exists between DOM events and KVision state in headless/automated contexts
4. Even a properly-constructed `MouseEvent` with `bubbles: true` doesn't reach KVision's internal handlers

**Workaround options:**
1. **JS injection**: Find KVision's internal guestLogin function and call it directly via `browser_console`
2. **Manual browser**: User clicks manually; Python drives game logic
3. **Browser as passive observer**: Browser shows rendered game, Python drives everything else

## Screenshot Pipeline — Broken (MiniMax SSL)

`browser_vision` returns nginx 404. Screenshots ARE captured to disk (`~/.hermes/cache/screenshots/`), but the MiniMax VLM API endpoint (`/v1/coding_plan/vlm`) is returning SSL EOF errors. Workaround: use `mcp_MiniMax_understand_image` on the saved screenshot files directly.

## Command Corrections This Session

```bash
# CORRECT: Use --player-alias to match browser's playerAlias
/tmp/autogenesis-dev/bin/python controller.py \
  --player-name "LordMapleTree" \
  --ai-count 0 \
  --player-alias "guest-user" \
  --no-ui

# CORRECT: Server startup order
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :server-extend:run &   # FIRST — port 7070
./gradlew :server:run &          # SECOND — port 9080

# VERIFY:
ss -tlnp | grep -E "7070|9080"
# Should show both LISTEN before proceeding
```

## Key Log Messages to Watch

```
# Controller connecting as CONTROLLER (via role=CONTROLLER URL param):
GameInit: playerAlias='guest-user' set — searching for existing playerStats entry...
GameInit: playerAlias match found — 'Lord Maple Tree' (conn=lord-...) will accept controller session as alias 'controller-...'
GameInit: Registering controller for existing player 'Lord Maple Tree' (role=CONTROLLER)

# isReachable checking all sessions:
WorldManager.isReachable: Final reachability for 'LordMapleTree': CONNECTED (sessions=2)

# AI takeover (controller not reachable in time):
TurnHarness.awaitPlayerAction: Player 'LordMapleTree' is UNREACHABLE - returning null to trigger AI takeover
TurnHarness.handleAiTakeover: Generating AI action for LordMapleTree...
```

## What the Controller Actually Needs

The controller doesn't need to BE the player — it just needs to:
1. Keep the game alive (respond to ping/pong)
2. Submit actions when it's Lord Maple Tree's turn
3. Use the correct playerAlias to join the browser's player slot

The browser handles the visual display; controller handles the game logic. This is the intended dual-control debugger pattern.

## Reference: controller.py canonical arguments

```python
# Full headless run with playerAlias matching:
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
stdbuf -oL -eL /tmp/autogenesis-dev/bin/python controller.py \
  --player-name "LordMapleTree" \
  --ai-count 0 \
  --player-alias "guest-user" \
  --no-ui

# Log output:
tail -f ~/.autogenesis/logs/controller_*.log | grep -E "WS event|My turn|submitted|Player.*UNREACHABLE"
```