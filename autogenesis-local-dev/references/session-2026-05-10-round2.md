# Round 2 Bug Hunt — 2026-05-10

## Session Overview

Session 1 of 10. Browser stuck on main menu → halted and reported. All servers stopped.

## What We Ran

- server-extend (7070) + game server (9080) + webpack (8080) — all clean startup
- Python controller `--no-ui --player-alias guest-user --ai-count 0`
- Matchmaking via Python REST → success
- 2 rounds executed server-side (fallback actions — TPipe embedded in Java)

## Key Finding: TPipe DynamoDB Errors Are a Red Herring

**Root cause identified:** An alien **DynamoDB Local Docker container** (`9afd9cb57d49`, started May 8) was running on port 8000, intercepting the Python controller's `tpipe_client` requests.

The Python controller's `tpipe_client` hits `http://127.0.0.1:8000/` — but TPipe is NOT externally callable. TPipe is embedded in the Java game server JVM and calls AWS Bedrock internally. The DynamoDB 400 error was from the stray container, NOT from TPipe.

**Fix applied:** `docker stop 9afd9cb57d49 && docker rm 9afd9cb57d49`

The game was never actually impacted. The "fallback" was always triggered intentionally because the `tpipe_client` is a separate broken mechanism. The game server's internal TPipe works fine.

## New Bug Status

| Bug | Status |
|-----|--------|
| #1 Server 15s shutdown | PROBABLE — server held by Python controller WS |
| #2 AI thinking vanishes | PARTIAL FIX — `findAllSessions` applied; browser can't verify |
| #3 NPC thinking capture | No bug found (hostile review confirmed) |
| #4 Writing UI stuck | CANNOT PROVE — browser stuck on main menu |
| #5 Reasoning [] | CANNOT PROVE — browser stuck on main menu |
| #6 Nemesis alert | CANNOT PROVE — karma threshold not crossed |
| #7 Blue person icon | CANNOT PROVE — browser never reached gameplay |
| #8 Eligible NPC flood | CONFIRMED + FIXED — `!isDefeated` at TurnHarness.kt:1530 |
| #9 Too many nemesis | NOT OBSERVED — karma too low |
| #10 Counterplay cascade | NOT OBSERVED — no counterplay |
| #11 Elder God generic | CANNOT PROVE — no elder god spawned |

## Remaining Blocker

Browser `skipLogin=true` mode bypasses matchmaking — `World.localPlayer` never gets set. Browser stays on main menu. For the remaining bugs to be proven, browser needs full REST matchmaking via `server.extend.requestGame`.

## TPipe Architecture Clarification

- TPipe = Kotlin library embedded in Java game server JVM (TPipe/TPipe project as Gradle dependency)
- Python controller's `tpipe_client` on port 8000 = unrelated broken mechanism
- DynamoDB Local Docker on 8000 = alien container unrelated to Autogenesis (started May 8, likely from Claude Code Discord bot project)
- Port 8000 now free — `tpipe_client` will get "connection refused" (cleaner than DynamoDB 400)