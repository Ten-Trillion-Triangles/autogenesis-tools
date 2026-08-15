# Session 2026-05-08 Late — Turn Detection Confirmed, :server Project Name Fixed

## :server vs :game — Critical Fix

The game server Gradle project is named `:server`, NOT `:game`.

```bash
# WRONG — fails with "project 'game' not found":
./gradlew :game:run

# CORRECT:
./gradlew :server:run
```

Verify with: `./gradlew projects -q | grep -E "server|kvision"`

## Server Startup

- server-extend (proc_82569cd89b0a): `./gradlew :server-extend:run` → port 7070 LISTEN
- game server (proc_51eacc064c0f): `./gradlew :server:run` → port 9080 LISTEN  
- webpack (proc_05a73837b62d): `./gradlew runKvisionNoHotReload` → port 8080 LISTEN
- Ports confirmed via `ss -tlnp | grep -E "7070|9080|8080"`

## Controller Test Run

Ran `controller.py --no-ui` successfully:

```
SSE session.ready detected
Matchmaking: server.extend.requestGame → HTTP 202
Lord Maple Tree's turn detected via ui.activeTurn + ui.setResolutionStep:START
Action submitted via game.submitAction
TPipe fallback triggered (expected — TPipe embedded in Java)
```

Pong thread, SSE reader, and turn detection all working correctly.

## Key Observations

1. **`:server` not `:game`** — confirmed via `./gradlew projects` output showing `Project ':server'`
2. **TPipe embedded** — DynamoDB at :8000 is separate service; TPipe runs inside Java JVM via gRPC on 9091
3. **Browser automation broken for KVision** — confirmed again; use Python REST matchmaking
4. **Playwright browser holder** — can observe but not drive UI; killed process proc_3ff8b522cd43
5. **All servers operational** — SE (pid 1693951), game (pid 1695288), webpack (pid 1696063)

## Skill Updates Applied

- `autogenesis-local-dev` SKILL.md: added NOTE about `:server` (not `:game`) in startup commands
- `autogenesis-local-dev` SKILL.md: corrected `pkill` command to include `gradlew` (not `webpack`)
- `autogenesis-local-dev` SKILL.md: added session state block at top of SKILL.md

## Session Note

This session was primarily a review/grounding conversation. No new bugs found, no new techniques discovered beyond the `:server` project name correction. Game running normally.