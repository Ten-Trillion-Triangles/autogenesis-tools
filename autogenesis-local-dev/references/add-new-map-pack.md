# Adding a New Map Pack to the Server

Companion to `references/map-pack-update-pattern.md` (which covers editing an existing pack's data without disturbing its PNG). This reference covers installing a brand-new pack end-to-end: drop into `server/src/main/resources/maps/`, verify schema, decide whether to wire it into a player-count pool.

## When to use this

- User provides a `.map` file and says "install it" / "add it" / "put it in the game"
- User names a target player count (e.g. "this is a 4-player map", "use this for 3-player games")
- You need to confirm the file will load before restarting the server

## The Iron Rule (scope)

The maps directory is exactly:

```
server/src/main/resources/maps/
```

The `kvisionApp/src/jsMain/resources/maps/*.zip` and `mapEditor/src/jsMain/resources/maps/*.zip` files are unrelated (JS-side bundles / editor fixtures). Do not touch them unless the user explicitly names them. See `references/map-system.md` "Where Maps Live" for the full directory map.

## Map Pack Format Reminder

Despite the `.map` extension, each file is a **ZIP archive** (PK\x03\x04 magic bytes) with exactly two STORED entries:

```
<name>.map
├── map.json      — loader-facing metadata
└── <image>       — PNG/JPEG background (e.g. map.png, laurasia_gondwana.png, san_martello.png)
```

The `image` filename is whatever the map editor chose; the loader reads `map.json: imageName` to bind the bytes back together. The image can be any filename — there's no convention enforced.

## The Safe Install Procedure

### 1. Drop the file in (the one-line part)

```bash
cp <source>.map server/src/main/resources/maps/<name>.map
```

`MapResourceRegistry.listPackagedMaps()` scans the classpath; the new file is reachable on next server start with **no code change**. It will land in the random-fallback pool only.

### 2. Verify schema BEFORE restarting the server

```bash
python3 ~/.hermes/skills/gaming/autogenesis-local-dev/scripts/verify-map-pack.py \
  server/src/main/resources/maps/<name>.map
```

The verifier checks:
- Magic bytes = `PK\x03\x04` (real ZIP, not renamed JSON)
- `map.json` parses as JSON
- Top-level keys include `imageName` and `mapData`
- `mapData.pins[]` non-empty, every pin has `pinId` and `territory`
- `mapData.connections[]` present and consistent (every `fromPinId`/`toPinId` resolves to a real pin)
- The image entry referenced by `imageName` exists in the zip
- Pin/connection counts vs. player-count archetype (see fingerprint below)
- Reports the matching schema variant (full vs. skeleton) — **either is loadable**, this is informational

If the verifier returns non-zero, fix the file source and re-run. Do NOT wire it into a pool until the verifier passes.

### 3. Decide whether to wire it into a player-count pool

If user says "use this for N-player games" / "this is an N-player map" / similar, edit `GameInit.kt`. **Two** random pools are editable, both in `server/src/main/kotlin/gameInit/GameInit.kt`:

- **2-player pool** at lines 153-162:
  ```kotlin
  // GameInit.kt:153-162
  if(totalPlayers == 2)
  {
      // Randomly pick one of the 2-player maps (fixedUSamerica, San_Martello, Arctica)
      val twoPlayerMaps = listOf(
          "maps/fixedUSamerica.map",
          "maps/San_Martello.map",
          "maps/Arctica.map"
      )
      val chosen = twoPlayerMaps[kotlin.random.Random.nextInt(twoPlayerMaps.size)]
  ```
- **3-4 player pool** at lines 171-177:
  ```kotlin
  // GameInit.kt:171-177
  // Randomly pick one of the 3-4 player maps (IO-map, Laurasiagondwana, jupiter, Europa)
  val threeFourPlayerMaps = listOf(
      "maps/IO-map.map",
      "maps/Laurasiagondwana.map",
      "maps/jupiter.map",
      "maps/Europa.map"
  )
  val chosen = threeFourPlayerMaps[kotlin.random.Random.nextInt(threeFourPlayerMaps.size)]
  ```

Append a trailing-comma line:

```kotlin
    "maps/San_Martello.map",
    "maps/Arctica.map",
    "maps/<NewMap>.map"   // ← add
)
```

**Pitfall: silent failure.** If the path string doesn't match a file on disk in `server/src/main/resources/maps/`, `WorldManager.loadMapFromResources()` throws, the catch block in `GameInit.kt` logs a warning, and the session falls through to `MapSelectionService.loadRandomMapPack()`. The map is never picked via the pool — it's still in the random pool because `MapResourceRegistry` finds it, but the editorial intent (4-player uses this map) is lost. **Always verify filename spelling with `ls server/src/main/resources/maps/` after the edit.**

There is no 5-8 player pool.

### 4. Ad-hoc verification (no canonical build needed)

For a one-line map-list edit, a full Gradle build is wasteful. Use the verifier script:

```bash
python3 ~/.hermes/skills/gaming/autogenesis-local-dev/scripts/verify-map-pack.py \
  server/src/main/resources/maps/<YourMap>.map
```

Plus a `grep -rn "YourMap" server/src/main/` to confirm no orphan references and a `ls server/src/main/resources/maps/` to confirm the file is on disk. Anything more requires the dev server up.

## Player-Count Archetype Fingerprint (pin/connection counts)

Empirically observed 2026-07-06 (before adding Europa, all counts via verifier):

| Map | Pins | Connections | Schema variant | Player count (pool) |
|---|---|---|---|---|
| fixedUSamerica | 47 | 246 | skeleton | 2 (primary) |
| San_Martello | 49 | 242 | skeleton | 2 (primary) |
| Arctica | 58 | 348 | full | 2 (added 2026-07-06) |
| Europa | 75 | 442 | full | 3-4 (added 2026-07-06) |
| Laurasiagondwana | 90 | 380 | full | 3-4 |
| jupiter | 87 | 696 | full | 3-4 |
| IO-map | 94 | 446 | skeleton | 3-4 |

**Decision rule of thumb:**
- 2-player pool: 47-58 pins / 240-350 conns as of 2026-07-06. Pin count is what matters; Arctica pushed the upper bound up from the original ~50. >75 pins in a 2-player map will likely feel cramped or oversized — flag as a playtest.
- 3-4 player pool: 75-94 pins / 380-700 conns. The cluster is clear; >100 pins or >800 conns may stress BFS targeting / territory threshold scoring — flag for playtest.
- Below 47 pins: probably a single-player or test fixture, do not pool as a player-count map.

These are decision-support only. The actual load-bearing compatibility is "the loader doesn't throw" — which the verifier proves by JSON-shape, not by counts. Counts are about whether the map will be FUN at the assigned player count.

## Common Mistakes (Don't)

- **Trusting the file extension.** `.map` does NOT mean JSON. Always check magic bytes (`PK\x03\x04`).
- **Trusting size comments.** Some forums list "~240-700 connections" as a hard limit; it's not. Europa is 442 and ships fine. The shape check matters more.
- **Trusting `verifyMapPack=true` to mean "will run."** The verifier is an ad-hoc shape check. `WorldManager.loadMapFromResources()` does the real loading — and only a Gradle boot exercises it.
- **Adding the map and skipping the `GameInit.kt` edit when the user asked for player-count assignment.** The map is reachable via the random pool without the edit, but the user said "4-player" and the random pool is not 4-player-only.
- **Sharing a verifier script between `/tmp` and the skill directory.** The canonical copy lives under `~/.hermes/skills/gaming/autogenesis-local-dev/scripts/`. Ad-hoc copies under `/tmp` are fine for one-shots; clean them up.
- **Touching kvisionApp e2e fixtures or mapEditor dev maps.** Scope discipline per "The Iron Rule" above.
- **Accepting Gradle's `UP-TO-DATE` / `FROM-CACHE` markers as proof.** When asked to verify by running the canonical test, the verification tracker compares the JUnit XML's `timestamp=` attribute against the wall clock. If the cached `results.bin` was emitted from a prior run, Gradle reuses it and the XML shows `timestamp=...minutes ago` — the system flags it as stale. Deleting the result XML does NOT invalidate `results.bin`. Use `--rerun-tasks` to force every task to re-execute, then re-check the XML timestamp. See "Step 4b: Force fresh canonical test execution" below.
- **Running a scoped test without `--offline` when sister Gradle subprojects are being edited.** TPipe subprojects (`:TPipe:compileKotlin`, `:TPipe:TPipe-Bedrock`, `:TPipe:TPipe-OpenRouter`, `:TPipe:TPipe-Defaults`, `:TPipe:TPipe-Ollama`) are siblings in the composite build. If another agent is mid-write on TPipe, `:server:compileKotlin` can fail with `Internal compiler error` / `DataFormatException` because the Kotlin daemon or `.gradle/caches` JARs are in flux. Always use `--offline` so Gradle doesn't try to refresh dep JARs mid-build. If you do see the `DataFormatException`, see "Step 4c: Cross-project Gradle collision" below.

### 4b. Force fresh canonical test execution

To prove the change runs end-to-end at the JVM classpath-discovery layer, extend `server/src/test/kotlin/org/ttt/autogenesis/server/maps/MapResourceRegistryTest.kt` to assert the new filename is in the discovered list (one `assertTrue` block per new map). Then run:

```bash
./gradlew :server:test \
    --tests "org.ttt.autogenesis.server.maps.MapResourceRegistryTest" \
    --console=plain --offline --rerun-tasks
```

The three non-obvious flags:
- `--tests "..."` scopes the JUnit run to one test method (cheaper than the full suite).
- `--offline` prevents Gradle from re-fetching dep JARs (avoids collision with another agent mid-write on TPipe — see "4c").
- **`--rerun-tasks` forces every task to re-execute, even when Gradle's task-cache says the result is fresh.** Without this, `:server:test` will reuse the cached `results.bin` and the JUnit XML will carry the prior run's timestamp — the verification tracker will mark it stale even though the test technically passed. Verify the captured XML has a `timestamp=` attribute within the last few seconds, AND that Gradle's output shows `:server:test` (not `UP-TO-DATE` and not `FROM-CACHE`):

```
> Task :server:test
BUILD SUCCESSFUL in 1m 18s
26 actionable tasks: 26 executed       (no cache hits)
```

A captured XML that satisfies all four:
```xml
<testsuite ... tests="1" failures="0" errors="0" timestamp="2026-07-06T23:07:39.482Z" hostname="cage-desktop" time="0.036">
```

If `tests="1"` becomes `tests="N"` with N>1, your `--tests` filter didn't apply — you're running the full server suite. If `failures > 0`, the test caught a real discovery-shape mismatch (typically: missing `.map` extension, wrong filename casing, or a corrupted zip — re-run the verifier first).

### 4c. Cross-project Gradle collision

When `:server:compileKotlin` or `:server:kspTestKotlin` fails with `java.util.zip.DataFormatException: invalid stored block lengths` / `zip END header not found`, the underlying cause is a corrupted dep JAR in `~/.gradle/caches/`, almost certainly because another agent's session is mid-write on a TPipe subproject that shares the composite build's classpath cache.

Recovery sequence (narrowest first):
1. **Audit + remove just the corrupt JARs** (the surgical fix). Any jar that fails `unzip -t` is the offender. Empty stub jars (like `instrumented-listenablefuture-9999.0-empty-*.jar`) are usually red herrings — the real culprit is a truncated fresh download.
   ```bash
   find ~/.gradle/caches -name "*.jar" 2>/dev/null \
     | xargs -P 8 -I{} sh -c 'unzip -t "$1" >/dev/null 2>&1 || echo "$1"' _ {} \
     > /tmp/hermes-verify-corrupt-jars.txt
   xargs rm -f -- < /tmp/hermes-verify-corrupt-jars.txt
   rm -f /tmp/hermes-verify-corrupt-jars.txt
   ```
2. **Clear KSP's test cache** (a separate but related path — KSP worker reads the dep JARs and can corrupt its own outputs):
   ```bash
   rm -rf server/build/kspCaches server/build/tmp
   ```
3. **Rerun with `--offline`** so Gradle doesn't try to refresh again from a flaky upstream:
   ```bash
   ./gradlew :server:test --tests "org.ttt.autogenesis.server.maps.MapResourceRegistryTest" \
       --console=plain --offline --rerun-tasks
   ```

If the collision persists (multiple agents hammering TPipe), scope even narrower — `:server:test --tests "..."` skips most module compilations but the Kotlin daemon must still resolve its own JAR classpath, which can hit the same race. In extreme cases, switch to a single-task `:server:compileTestKotlin` first to surface the failure before the test task consumes it.

## Worked Example (2026-07-06 — Europa installation)

1. Drop: `cp Europa.map server/src/main/resources/maps/Europa.map` (2.5 MB).
2. Verifier pass: 75 pins / 442 conns, full schema, image `map.png` present, JSON clean.
3. Pool edit: added `"maps/Europa.map",` to the `listOf(...)` at `GameInit.kt:171-177`.
4. Ad-hoc check: `grep -rn Europa server/src/main/` returned only the new lines; `ls server/src/main/resources/maps/` confirms 6 files now.
5. Outstanding: no Gradle boot / no live 4-player match smoke test — flagged to user as next-step verification, not done in-session.

The Europa case happens to fit the 3-4 archetype exactly (75 pins between Laurasiagondwana and IO-map). If a future map comes in at, say, 220 pins and 1,400 conns, the verifier still passes the schema check but the pool assignment gets a playtest caveat.

## Worked Example (2026-07-06 — Arctica 2-player install)

1. Drop: `cp Arctica.map server/src/main/resources/maps/Arctica.map` (6.1 MB).
2. Verifier pass: 58 pins / 348 conns, full schema, image `map.png` present.
3. Schema analysis: full schema (size/pointValue/resource/adjacentTerritoryNames all populated) with all-`Medium` size. Point values cluster at 3 (25) and 4 (17). Slightly above the 2-player archetype's previous upper bound (San_Martello at 49), but still in the same terrain.
4. Pool edit: appended `"maps/Arctica.map",` to the **2-player** `listOf(...)` at `GameInit.kt:153-162`. (This was previously treated as hard-coded — see "Step 3" above for the corrected view.)
5. Canonical verification:
   - Extended `MapResourceRegistryTest.listPackagedMaps_includesStartMap` with two more `assertTrue` blocks asserting `maps/Europa.map` and `maps/Arctica.map` are in `listPackagedMaps()`.
   - Ran `./gradlew :server:test --tests "org.ttt.autogenesis.server.maps.MapResourceRegistryTest" --console=plain --offline --rerun-tasks`.
   - Captured JUnit XML showed `timestamp="2026-07-06T23:07:39.482Z"` (within seconds of the wall clock at run time), `tests="1" failures="0" errors="0"`.
6. Outstanding: `WorldManager.loadMapFromResources` runtime path (zip parse + topology validation) is not exercised by `MapResourceRegistryTest`. A live 2-player match is the only true positive — flagged to user as next-step verification.

The Arctica extension flagged (and this SKILL.md captures) two new patterns not visible in the Europa session:
- **Verification staleness loop**: without `--rerun-tasks`, Gradle reuses the cached `results.bin` from the Europa run; the verification tracker sees a stale XML and prompts for re-verification. Three cycles in the same session before the fix landed.
- **Cross-project Gradle collision**: a parallel TPipe write during the Europa run left corrupted entries in `~/.gradle/caches/`. Recovery used the corrupted-jar audit + KSP cache purge + `--offline` sequence documented in Step 4c.

## Non-matchmaking install (tutorial / guided-walkthrough reserved map)

A map can be installed "without being assigned to a pool" if its intended entry point is a **deterministic-name loader** rather than a random roll — a guided tutorial, a single-player walkthrough, a benchmarking scene, etc. The risk: a map that exists on the classpath will be picked by `MapSelectionService.pickRandomDescriptor()` unless explicitly excluded. Putting it in `server/src/main/resources/maps/` is necessary AND sufficient for a deterministic loader to find it by name; **NOT** putting it in `GameInit.kt` pool lists is necessary for normal matchmaking to skip it; but exclusion is fragile because of Path 4 below.

### The 4 paths a map can be loaded into a session

Trace every code path that calls `WorldManager.loadMapFromResources(...)` or `MapSelectionService.loadRandomMapPack()`:

| Path | Source | Trigger | Recommended exclusion |
|---|---|---|---|
| 1 | `GameInit.kt` 2-player pool list (lines 153-162) | 2-player matchmaking | Omit from the list literal at line 157-161 |
| 2 | `GameInit.kt` 3-4 player pool list (lines 171-177) | 3-4 player matchmaking | Omit from the list literal at line 176-181 |
| 3 | `GameInit.kt` `allMaps` rigged-map find-list (lines 122-129) | CLI `--map=<name>` flag | Omit from `allMaps` literal at line 122-129 — `--map=tutorial` then fails cleanly to default selection |
| 4 | `MapSelectionService.pickRandomDescriptor()` (line 22-50) | Fallback when no specific map loaded (5+ players OR pool load throws) | Add to `excludedRandomPoolPaths` set in `MapSelectionService.kt:25-29`; filter via `.filterNot { path -> path in excludedRandomPoolPaths }` |

**Without Path 4 exclusion**, a tutorial-style map has a 1-of-N roll probability (currently 1/8 with 8 installed maps) of being randomly picked in any session that doesn't hit one of the player-count-specific pools. That's 12.5% for each fallback fire — small but non-zero, and infinite over time.

### Install recipe — non-matchmaking reserved map

Steps 1-2 are identical to the standard install. Steps 3-7 are the new ones:

1. **Drop the file in.** `cp <source>.map server/src/main/resources/maps/<name>.map`. No code change required for the loader to find it (`MapResourceRegistry` auto-discovers).
2. **Verify schema with `verify-map-pack.py <name>.map`.** Confirm loader-facing shape is clean.
3. **Do NOT touch the 2-player or 3-4 player pool lists in `GameInit.kt`.** Omission is the exclusion (less code than a guard).
4. **Do NOT touch the `allMaps` rigged-map list in `GameInit.kt`.** Same reasoning.
5. **Add the map to `excludedRandomPoolPaths` in `MapSelectionService.kt:25-29`:**
   ```kotlin
   private val excludedRandomPoolPaths: Set<String> = setOf(
       "maps/<YourMap>.map"
   )
   ```
   And confirm the `.filterNot` line is intact at line 36-37:
   ```kotlin
   val packaged = MapResourceRegistry.listPackagedMaps()
       .filterNot { path -> path in excludedRandomPoolPaths }
       .map { path -> ...
   ```
6. **Add a JUnit test that PINS the exclusion + the positive name-resolve path.** Copy the template from `server/src/test/kotlin/org/ttt/autogenesis/gameInit/MapSelectionServiceTest.kt::pickRandomDescriptor_excludesTutorialMap_butLoadBytesByNameStillResolvesIt` — it does the work in one method:
   - Sanity: assert `<YourMap>.map` is in `MapResourceRegistry.listPackagedMaps()` (so the determinism-side loader can find it).
   - Negative: 1000 random rolls of `pickRandomDescriptor()` must show **zero hits** for the excluded path.
   - Positive: `MapSelectionService.loadBytesByName("maps/<YourMap>.map")` must return non-empty bytes (so the tutorial entry code can load it deterministically).
7. **Run canonical verification** with `--rerun-tasks`:
   ```bash
   ./gradlew :server:test \
       --tests "org.ttt.autogenesis.server.maps.MapResourceRegistryTest" \
       --tests "org.ttt.autogenesis.gameInit.MapSelectionServiceTest" \
       --console=plain --offline --rerun-tasks
   ```
8. **Source-tree verification** for fast iteration before the Gradle build:
   ```bash
   python3 ~/.hermes/skills/gaming/autogenesis-local-dev/scripts/verify-map-exclusion.py <Name>
   ```
   Asserts all 4 exclusion sites are consistent (no edit needed in `GameInit.kt` to verify; just inspects the lists on disk plus the `excludedRandomPoolPaths` set in `MapSelectionService.kt`).

### Why the source-tree verifier is the cheap pre-check

The 4-path exclusion is structurally simple but the **interaction** is what makes the test: a single typo in `excludedRandomPoolPaths` and the test sees 1/8 hits instead of 0/1000. The Gradle test takes ~70 seconds including warm caches; the source-tree verifier is 50ms and can run pre-commit. Run both — neither alone is sufficient:
- **Source-tree verifier alone**: confirms the exclusion code is present — yes/no, doesn't catch semantic bugs (wrong filename spelling).
- **Gradle test alone**: works, but a manual cost of ~1m per rerun. Use as the final gate.

### Common mistakes

- **Assuming "off the list" means "can't roll."** Path 4 (the random fallback) IGNORES the pool lists. Adding a map AND omitting it from `excludedRandomPoolPaths` is the most common 12.5% probability bug. The 1000-roll test is the only way to catch this.
- **Adding to `excludedRandomPoolPaths` without updating the test.** The verifier doesn't know about exclusion — it only checks schema. Run both.
- **Adding a tutorial flag in `map.json` for the code to read.** The `mapData` keys `worldName`, `author`, etc. are NOT used for routing — `GameInit` and `MapSelectionService` match on the filename string only. If you want the dispatcher to differentiate tutorial maps, the cleanest mechanism is the `excludedRandomPoolPaths` set + a future name-based dispatch on the rigMap-style list, not metadata.
- **Editing `GameInit.kt` to add the map as the only entry of a new pool.** Structurally valid but creates a pool nobody calls. Don't.
- **Distrusting the test package path.** `MapSelectionServiceTest` lives at `server/src/test/kotlin/org/ttt/autogenesis/gameInit/MapSelectionServiceTest.kt` (the package is `org.ttt.autogenesis.gameInit`, not `org.ttt.autogenesis.gameInit.MapSelectionService`). If a future test method passes when it should fail, check the package + import first.
- **Hardcoding the PNG filename in your own verifier.** Bundled maps use `map.png`; tutorial.map uses `tutorial map.png` (with a space); other packs use whatever the editor chose (e.g. `san_martello.png`). Always read the value from `map.json:imageName` rather than asserting a literal name.

### Worked Example (2026-07-06 — tutorial.map install)

1. Drop: `cp tutorial.map server/src/main/resources/maps/tutorial.map` (2.5 MB). Note the file's PNG is named `tutorial map.png` — the verifier (which reads `imageName` from `map.json`) handles it cleanly. An ad-hoc verifier that hard-codes `map.png` will produce a false negative.
2. Verifier pass: 11 pins / 42 conns (far below the 47-58 2-player archetype — appropriate for a guided tutorial). All `Medium` size, `worldName='Tutorial'`. Schema full (`size`/`pointValue`/`resource`/`adjacentTerritoryNames`).
3. **NOT added to any `GameInit.kt` pool list** — structural exclusion. Verified via `grep "tutorial" server/src/main/kotlin/gameInit/GameInit.kt` (zero matches in pool lists).
4. `MapSelectionService.kt` patches: added `excludedRandomPoolPaths = setOf("maps/tutorial.map")` + `.filterNot { path -> path in excludedRandomPoolPaths }` after `listPackagedMaps()`.
5. New test method `pickRandomDescriptor_excludesTutorialMap_butLoadBytesByNameStillResolvesIt` (1000 rolls, 0 hits + positive resolve).
6. Canonical Gradle run with both test classes scoped + `--rerun-tasks`:
   - `MapResourceRegistryTest`: `tests="1" failures="0" errors="0" timestamp="2026-07-06T23:18:29.793Z"`
   - `MapSelectionServiceTest`: `tests="4" failures="0" errors="0" timestamp="2026-07-06T23:18:29.429Z"`
7. Subsequent ad-hoc script run flagged the test had a false-negative (the script asserted `entries >= {"map.json", "map.png"}` but tutorial.map's PNG is `tutorial map.png` with a space). The canonical Gradle test was unaffected because it doesn't unpack the PNG entry — only the ad-hoc source-tree script tripped. **Rule:** don't trust ad-hoc verifiers that hard-code filenames; read the value from `map.json`.

### Outstanding for this class

- **Future tutorial entry RPC.** `MapSelectionService.loadBytesByName("maps/tutorial.map")` is the contract for whatever guided-entry code lands next. Add a JSON metadata field like `mapData.isTutorial: true` on re-export only if dispatcher-side differentiation is wanted, or stick with the deterministic-name convention.
- **Live match smoke test.** `WorldManager.loadMapFromResources("maps/tutorial.map")` runtime topology validation (11 pins / 42 conns is well below all bundled archetype minimums — BFS targeting / threshold scoring may need adjustment). A live solo 2-player session is the only way to know.
