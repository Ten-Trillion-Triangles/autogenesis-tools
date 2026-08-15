# Dual-Control Debugger Architecture (2026-05-08)

Python controller (CONTROLLER) and browser (PRIMARY) can now coexist on the same player slot in the game server. This enables the "Autogenesis debugger" pattern where Python drives the game while the browser serves as a passive visual observer.

## What Was Built

### Phase 1: `GameRequest.playerAlias` (sharedModel)
`sharedModel/src/commonMain/kotlin/structs/matchmaking/GameRequest.kt` — added `playerAlias: String = ""` to the shared `GameRequest` data class. This is what the Python controller sends to request joining the browser's existing game session.

### Phase 2: `PlayerConnectionManager` Multi-Session (server)
`server/src/main/kotlin/org/ttt/autogenesis/server/PlayerConnectionManager.kt`:
- Sessions stored as `ConcurrentHashMap<String, MutableList<PlayerSession>>` — append-only, never replaces sessions
- `findSession()` — returns first session (unchanged)
- `findAllSessions()` — NEW — returns all sessions for a playerId
- `hasPrimarySession(playerId)` / `hasControllerSession(playerId)` — NEW — query session role existence
- `deregister(session)` — removes specific session, not entire playerId
- Shutdown logic updated: only triggers when neither PRIMARY nor CONTROLLER sessions remain

### Phase 3: `SessionRole` enum + Server.kt URL param (server)
`server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt`:
- `SessionRole.PRIMARY` (browser) vs `SessionRole.CONTROLLER` (Python)
- Parses `?role=CONTROLLER` from WebSocket URL, defaults to `PRIMARY`
- Passes role to `connectionManager.register(playerId, wsSession, sessionRole)`

### Phase 4: `WorldManager.isReachable` — ping ALL sessions (server)
`server/src/main/kotlin/gameState/WorldManager.kt`:
Changed to use `findAllSessions()` and ping each session sequentially. Player is reachable if **any** session (browser PRIMARY or Python CONTROLLER) responds to ping.

**Bug fixed:** `connectionManager?.findSession(playerId)` → `connectionManager?.findAllSessions(playerId) ?: emptyList()`. The nullable `connectionManager` needs `?.` safe call on `ping()` too.

### Phase 5: `PlayerSessionBundle.playerAlias` + `GameInit` matching (server + sharedModel)
`sharedModel/src/commonMain/kotlin/structs/matchmaking/SessionStatus.kt`:
- Added `playerAlias: String = ""` to `PlayerSessionBundle`

`server/src/main/kotlin/gameInit/GameInit.kt` — `configurePlayersFromSession`:
- When `playerAlias` is non-blank, searches existing `playerStats` for a matching entry
- Matching: `stats.playerID.contains(bundle.playerAlias) || stats.playerData.name.contains(bundle.playerAlias)`
- If found: controller's connectionId overwrites the existing entry — controller inherits the browser's player slot
- If not found: falls through to normal player registration

### Phase 6: Python controller updated (controller.py)
`controller/controller.py`:
- `CONFIG["player_alias"]` — stable identifier, auto-extracted from player_id mid-segment
- `--player-alias` CLI flag for manual override
- `MatchmakingClient.request_game()` — sends `playerAlias` in payload
- `GameController.__init__` — extracts `player_alias` from `player_id` (e.g., `lord-1234567890-ABC` → alias `1234567890`)
- `self.player_alias` stored on `GameController` instance for use in matchmaking

## Connection Flow

```
Browser connects (PRIMARY):
  ws://127.0.0.1:9080/events?playerId=browser-xxx&role=primary
  → PlayerConnectionManager.register("browser-xxx", ws, PRIMARY)
  → WorldManager.playerStats["browser-xxx"] = BrowserPlayer

Python connects (CONTROLLER) with playerAlias:
  ws://127.0.0.1:9080/events?playerId=controller-yyy&role=controller
  → PlayerConnectionManager.register("controller-yyy", ws, CONTROLLER)
  → PlayerConnectionManager.findAllSessions("browser-xxx") → [..., CONTROLLER session]

  Matchmaking request_game includes playerAlias="browser-xxx-midpart"
  → GameInit.configurePlayersFromSession: playerAlias match found
  → WorldManager.playerStats["browser-xxx"].playerID = "controller-yyy"
  → Browser's slot now uses controller's connectionId for ping routing

WorldManager.isReachable("controller-yyy"):
  → findAllSessions("controller-yyy") → [PRIMARY (browser), CONTROLLER (controller)]
  → ping PRIMARY → SUCCESS → reachable = true
  → game continues
```

## Python Controller Startup

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller

# Auto-extract alias from player_id (e.g., lord-1234567890-ABC → 1234567890)
stdbuf -oL -eL /tmp/autogenesis-dev/bin/python controller.py --no-ui

# Manual alias override
stdbuf -oL -eL /tmp/autogenesis-dev/bin/python controller.py --no-ui --player-alias 1234567890
```

## How playerAlias is Extracted

```python
# From GameController.__init__
parts = self.player_id.split("-")  # "lord-1234567890-ABC" → ["lord", "1234567890", "ABC"]
self.player_alias = CONFIG["player_alias"] or (parts[1] if len(parts) > 1 else self.player_id)
# → "1234567890" (stable middle segment)
```

The browser's `kvision-ws-*` ID contains the same timestamp format, so the alias from the browser's ID can be extracted and passed to Python via `--player-alias`.

## Server-Side Key Files (changed 2026-05-08)

| File | Change |
|------|--------|
| `sharedModel/.../GameRequest.kt` | `playerAlias: String = ""` |
| `sharedModel/.../SessionStatus.kt` | `playerAlias: String = ""` on `PlayerSessionBundle` |
| `server/.../PlayerConnectionManager.kt` | multi-session map, `findAllSessions`, `hasPrimarySession`, `hasControllerSession` |
| `server/.../Server.kt` | `?role=CONTROLLER` URL param, session role passed to register |
| `server/.../WorldManager.kt` | `isReachable` pings all sessions, nullable safe call fix |
| `server/.../GameInit.kt` | `configurePlayersFromSession` matches on playerAlias |
| `controller/controller.py` | `--player-alias` flag, `player_alias` in request_game payload |

## Build Verification

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :server:compileKotlin :server-extend:compileKotlin :sharedModel:compileKotlinJvm --no-daemon -q
# Must pass cleanly — compilation is the gate for all Kotlin changes

./gradlew :server:test --no-daemon -q
# 137 tests completed, 12 failed (pre-existing MockK issues in SummitOrchestratorTest)
# Failures are unrelated to these changes
```