# audioTracks Field Leaking into Agent Prompts

**Session:** 2026-07-24. Full source-level audit + fix implementation.

---

## Original Finding (Audit)

The `audioTracks` field on `World` (a `@Serializable` `AudioTracks` struct containing 9 music track lists: `drone`, `melody`, `rhythm`, `harmony`, `menu`, `start`, `nemesis`, `end`, `channels`) was dumped into 8 agent prompts via 10 `serialize(WorldManager.world)` call sites. The `com.TTT.Util.serialize()` (TPipe `Util/Util.kt:48`) uses kotlinx.serialization with `encodeDefaults = false`, but at runtime after the loader runs, `audioTracks` is fully populated, so all 9 lists serialize into the JSON.

### The 10 Call Sites (Original Audit)

| File | Line | Agent |
|------|------|-------|
| `builders/gameplayActions/npcHostileAgent.kt` | 165 | Hostile NPC |
| `builders/gameplayActions/npcActorAgent.kt` | 112 | NPC Actor |
| `builders/gameplayActions/nemesisAgent.kt` | 287 | Nemesis |
| `builders/gameplayActions/elderGodAgent.kt` | 239 | Elder God |
| `builders/judgeOutcome/judge.kt` | 2205 | Judge |
| `builders/judgeOutcome/geoPoliticsAssessmentAgent.kt` | 572 | GeoPol Assessor |
| `builders/playerAgent/playerAgent.kt` | 208, 313 | Player Agent × 2 |
| `builders/gatherContext/newcharacterscan.kt` | 665 | New Character Scan |

The `judge.kt:2202` call `serialize(WorldManager.world.npc.map { ... })` is NOT a world dump — it serializes a transformed NPC list. Do not touch that line.

### Why Not Just Add `@Transient`?

The obvious fix — `@kotlinx.serialization.Transient` on `audioTracks` — breaks the snapshot path. `GameSnapshot` carries `val world: World` (no `@Transient`), and `TurnHarness.serializeCurrentWorldSnapshotToUserRecord` serializes the snapshot to VFS. Existing saves have `audioTracks` in them. Making it transient would silently drop the audio state on every restore until the loader runs unconditionally — and the `applyGameSnapshot` call site in `TurnHarness.kt:2067` does NOT re-run the loader. `loadAudioTracksFromResource` is only called once at game init from `GameInit.kt:241`.

---

## The Actual Fix (Implemented 2026-07-24)

### Architecture: Helper at the Agent-Prompt Boundary

Added a `serializeWorldForAgentPrompt(world: World): String` helper in `sharedModel/src/jvmMain/kotlin/org/ttt/autogenesis/AgentWorldSerialization.kt`. It uses `world.copy(audioTracks = AudioTracks())` to produce a copy with empty audio lists, then serializes the copy via a kotlinx.serialization `Json` instance that mirrors `com.TTT.Util.serialize`'s configuration (ignoreUnknownKeys, isLenient, encodeDefaults=false).

**Why this works:** the helper is a pure function over `World`. The input world is not mutated. The agent prompts now receive a JSON payload without the `audioTracks` key, while the runtime music picker reads `WorldManager.world.audioTracks` directly off the live object (`TurnHarness.runtimeMusicCatalog()` at `TurnHarness.kt:119-120`) and is unaffected by the serializer path.

### Locations of the 10 Migrated Call Sites (Post-Fix)

| File | Line | Replacement |
|------|------|-------------|
| `builders/gameplayActions/npcHostileAgent.kt` | 166 | `serializeWorldForAgentPrompt(WorldManager.world)` |
| `builders/gameplayActions/npcActorAgent.kt` | 113 | was `com.TTT.Util.serialize(...)`, now the helper |
| `builders/gameplayActions/nemesisAgent.kt` | 287 | collapsed 2 lines into 1 |
| `builders/gameplayActions/elderGodAgent.kt` | 240 | helper |
| `builders/judgeOutcome/judge.kt` | 2206 | helper (line 2202 left untouched) |
| `builders/judgeOutcome/geoPoliticsAssessmentAgent.kt` | 573 | helper |
| `builders/playerAgent/playerAgent.kt` | 209, 314 | both replaced; `replace_all=true` required |
| `builders/gatherContext/newcharacterscan.kt` | 666 | helper |

### New Test Files

- `server/src/test/kotlin/agent/builders/SerializeWorldForAgentPromptTest.kt` — 3 tests: excludes audioTracks key, preserves other fields, no mutation of input
- `server/src/test/kotlin/agent/builders/SerializeWorldForAgentPromptIntegrationTest.kt` — 1 test: realistic world payload, stripped < baseline
- `server/src/test/kotlin/agent/builders/AudioTracksLoaderSmokeTest.kt` — 1 test: bundled `audio/audio-tracks.json` loads 78 tracks (drone=17, melody=21, rhythm=16, harmony=21, initial=1, nemesis=1, terminal=1)

The test filter `:server:test` only includes `agent.builders.*`, `agent.runners.*`, `agent.math.*`, `agent.debugTrace.*` packages by default. Place new agent tests in `agent.builders.*` to avoid the "no tests found" filter miss.

---

## Recipe Lessons (The Bugs Caught During Implementation)

### Lesson 1: Verify the WHOLE Pipeline, Not Just the Changed Package

Running the test suite scoped to the touched package (`agent.builders.*`) showed 0 failures. The actual regression was in `org.ttt.autogenesis.server.TurnHarnessRunningGameTest` (a test in a non-touched package). The wider scope `./gradlew :server:test --tests 'agent.builders.*' --tests 'org.ttt.autogenesis.server.*'` caught it.

**Rule:** when migrating a call site in a multi-package Kotlin project, run the test suite for the changed package AND the most-likely-impacted adjacent package (in this case the restore path / WorldManager mutation surface, which lives in `org.ttt.autogenesis.server.*`). Never trust a single-package green run when the change touches shared state.

### Lesson 2: `kotlinx.coroutines.sync.Mutex` Is Non-Reentrant

The original plan included a "defensive rehydrate" — call `WorldManager.loadAudioTracksFromResource("audio/audio-tracks.json")` inside `applyGameSnapshot`'s `worldMutex.withLock { ... }` block. The intent was that any future save that lost `audioTracks` would re-load the bundled resource on restore.

`loadAudioTracksFromResource` is `suspend` and internally calls `WorldManager.worldMutex.withLock { ... }`. Calling it from inside another `worldMutex.withLock` on the same coroutine throws `IllegalStateException("Already locked by this coroutine")` because `kotlinx.coroutines.sync.Mutex` is non-reentrant. The throw broke the restore path mid-flight — `WorldManager.world = snapshot.world` was executed but the rest of the state was lost, leaving `activeTurnActor` stuck at a stale value, which caused `TurnHarnessRunningGameTest > restoreWorldFromUserRecord does NOT arm the turn timer when NPC was active` to fail with `was: <Commander Shepard>` (the test expected NOT "Commander Shepard" because the NPC was the active actor).

**Rule:** never nest `worldMutex.withLock` calls. If a function takes `worldMutex`, it must be called from outside any lock that holds `worldMutex`. The "defensive rehydrate" was over-engineering — the snapshot's `audioTracks` field already round-trips through `serialize`/`deserialize` (since `World.audioTracks` is `@Serializable`), so re-loading on restore is unnecessary. **The fix was to remove the rehydrate entirely.**

### Lesson 3: System "Verification Unverified" Signals Are Real

The system flagged "unverified" twice with this exact message: *"No canonical test/lint/build command was detected."* The fix was to write an ad-hoc verification script under `/tmp` with a `hermes-verify-` prefix and run the WIDER test scope (not just the touched package). Cached reports are insufficient — use `--rerun-tasks` to force fresh execution.

**Rule:** when the system flags verification as unverified, write a fresh receipt by (1) running the canonical command with `--rerun-tasks`, (2) widening the test scope to all packages that could plausibly be impacted, (3) parsing the resulting XML reports, (4) writing a `/tmp/hermes-verify-*.txt` file with explicit per-class and per-system-test results.

### Lesson 4: Patch Tool Parameter Drop on Repeated Invocations

The `patch` tool sometimes drops the `path` parameter when calling with multiple string arguments in close succession. The reliable workaround is `execute_code` with imports: `from hermes_tools import patch; patch(path=..., old_string=..., new_string=...)`. This bypasses any parameter-serialization glitch the CLI dispatcher has.

---

## Final Verification (315 Tests, 0 Failures)

```
./gradlew :server:test --rerun-tasks \
  --tests 'agent.builders.*' \
  --tests 'org.ttt.autogenesis.server.*'
```

Result: 315 tests across 53 classes, 0 failures, 0 errors. All 3 new tests pass. `TurnHarnessRunningGameTest` (25 tests) passes. The defensive rehydrate is NOT present in the final tree — `git diff HEAD server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt` shows 0 bytes changed.

---

## Why This Matters

The `audioTracks` payload is a music catalog — track names, URLs, channel hierarchy. When dumped into agent prompts:
- It inflates context size (all 9 track lists × AudioObject entries × channel nodes).
- It provides zero gameplay-relevant information to the agents.
- It may influence the LLM in unexpected ways depending on track names or descriptions.

The KDoc at `World.kt:31-38` says the intent is that `audioTracks` is a "runtime resource" (default-empty before loader runs, replaced post-init). The helper approach enforces that intent at the agent-prompt boundary while keeping the snapshot path intact for save/restore.

