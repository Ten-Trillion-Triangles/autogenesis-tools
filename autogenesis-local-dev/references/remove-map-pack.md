# Removing a Map Pack From the Server

Companion to `add-new-map-pack.md` (install) and `map-pack-update-pattern.md` (in-place edit). This reference covers removal: the inverse of install, scoped to `server/src/main/resources/maps/` only, with a negative-path regression pin to catch future re-addition.

## When to use this

- User says "remove this map" / "delete it" / "take it out of the game"
- Map is failing gameplay (the fixedUSamerica.map case: "use WMDs and sweep every tile every turn" — strategic-design failure)
- Map is being replaced by a new version (remove old, install new in same session)
- Map is a dead test fixture (rare — usually kept for editor use)

## The Iron Rule (scope)

Removals are scoped exactly like installs:

```
server/src/main/resources/maps/
```

**Do not** touch `kvisionApp/src/jsMain/resources/maps/*.zip` or `mapEditor/src/jsMain/resources/maps/*.zip` unless the user names them. These are separate filesystems with separate lifecycles:

- `server/src/main/resources/maps/*.map` — JVM classpath, picked by `MapResourceRegistry.listPackagedMaps()`
- `kvisionApp/src/jsMain/resources/maps/*.zip` — JS-side bundle, used by the lobby preview
- `mapEditor/src/jsMain/resources/maps/*.zip` — editor fixtures (dev only)

The 2026-07-06 fixedUSamerica.map removal is the canonical reference for the "server-only removal" pattern: server map file deleted, GameInit.kt lists purged, lobby bundle (`us-america.zip`) kept as-is per user choice. Lobby preview still surfaces the map but selecting it errors at the server.

## The 4 purge sites

| # | File | Section | Pattern |
|---|---|---|---|
| 1 | `server/src/main/resources/maps/<Name>.map` | file deletion | `rm <file>` |
| 2 | `server/src/main/kotlin/gameInit/GameInit.kt` | 2-player pool list | remove the line `"maps/<Name>.map",` |
| 3 | `server/src/main/kotlin/gameInit/GameInit.kt` | 3-4 player pool list | remove the line `"maps/<Name>.map",` (if applicable) |
| 4 | `server/src/main/kotlin/gameInit/GameInit.kt` | rigged-map `allMaps` find-list | remove the line `"maps/<Name>.map",` |

**Important: `MapSelectionService.kt` does NOT have a per-map entry for non-excluded maps.** The `excludedRandomPoolPaths` set only references maps that ARE installed but should NOT roll. For removal, the absence of the file on disk means `MapResourceRegistry.listPackagedMaps()` won't return it at all — no set edit needed.

## Why each step matters

- **Step 1 alone** would leave the file in the GameInit pool lists. Next server boot, the loader tries to find the resource, throws, the catch block at GameInit.kt falls through to `MapSelectionService.loadRandomMapPack()` — silent breakage. The map is gone from gameplay but the code still references it.
- **Steps 2-4 alone** would leave a stray `.map` file on disk. `MapResourceRegistry` still finds it via the random fallback (Path 4 in `MapSelectionService`), so it CAN still roll in fallback sessions with 1/N probability.
- **All four together** is the only complete removal.

## Side-fix: the `allMaps` list drift bug

When editing the rigged-map find-list (`allMaps = listOf(...)`), you often notice older maps that were never added. This is a recurring **maintenance hazard**: the allMaps list does NOT auto-sync with the pool lists. When you add a new map to a pool, check whether the allMaps find-list also needs the entry; otherwise `--map=<NewMap>` will silently fall through to default selection.

The fixedUSamerica-removal session (2026-07-06) discovered the allMaps list was **missing Europa and Arctica** — they had been added to their pools but not to the rigged-find-list. Pre-existing bug from prior installs. Fixed incidentally during cleanup. **Always audit the allMaps list when editing GameInit.kt pool lists** — the drift goes both ways.

## Recipe — 4 steps

1. **Drop the file:**
   ```bash
   rm server/src/main/resources/maps/<Name>.map
   ```
2. **Edit `GameInit.kt`** — remove three `"maps/<Name>.map",` lines:
   - `twoPlayerMaps = listOf(...)` (around line 157-161)
   - `threeFourPlayerMaps = listOf(...)` (around line 176-181, if applicable)
   - `allMaps = listOf(...)` (around line 122-129)
   Plus the leading comment line if the only mention of the removed map is in a comment:
   ```diff
   - // 2-player maps: fixedUSamerica, San_Martello
   + // 2-player maps: San_Martello
   ```
3. **Add a negative-path regression pin** in `server/src/test/kotlin/.../server/maps/MapResourceRegistryTest.kt`. Inside `listPackagedMaps_includesStartMap`:
   ```kotlin
   assertTrue(
       maps.none { it.equals("maps/<Name>.map", ignoreCase = true) },
       "Expected maps/<Name>.map to be ABSENT (removed <YYYY-MM-DD>: <reason>). Got $maps"
   )
   ```
   This catches future regressions where someone accidentally re-adds the file. **Do not skip this** — the negative pin is the durable artifact of the removal decision.
4. **Run canonical verification** with `--rerun-tasks`:
   ```bash
   ./gradlew :server:test \
       --tests "org.ttt.autogenesis.server.maps.MapResourceRegistryTest" \
       --console=plain --offline --rerun-tasks
   ```
   The negative-pin passes (no `<Name>.map` in the list). Source-tree verifier also available — see `scripts/verify-map-removal.py`.

## Source-tree verifier (pre-check, ~50ms)

`scripts/verify-map-removal.py <MapName>` checks all 4 purge sites are consistent (file gone, 3 list entries gone, no other code references, negative-pin present). Run BEFORE the Gradle build as a fast iteration loop — surfaces typos and stale comments without paying the ~70s Gradle startup cost.

## Common mistakes

- **Deleting the .map file but leaving the `GameInit.kt` entries.** Symptom: next server boot, every 2-player matchmaking throws and falls through to the random pool (silent breakage). The negative test catches this only partially — `MapResourceRegistry.listPackagedMaps()` won't return the deleted map, which is exactly what the test asserts, so the test PASSES even if GameInit is still broken. The source-tree verifier catches the GameInit residue directly; the Gradle test does not (it only exercises `MapResourceRegistry`, not GameInit pool selection). Always run both.
- **Removing the `us-america.zip` lobby bundle when the user asked for server-only removal.** The server JVM classpath (`server/src/main/resources/maps/*.map`) and the KVision frontend bundle (`kvisionApp/src/jsMain/resources/maps/*.zip`) are **two separate filesystems**. A "remove" instruction applies to one by default; ask which before touching the other. As of 2026-07-06, the user's canonical answer was "server-only" for the fixedUSamerica case — the lobby still shows the map preview but selecting it from JS fails at the server side. Flag this as a follow-up if the user's stated intent was a complete removal.
- **Stale references in comments.** `// 2-player maps: fixedUSamerica, San_Martello` at the top of `GameInit.kt`. If the only mention of the removed map's name is in a comment, remove it. Leaving stale references in comments is a future-confusion footgun.
- **Removing `<Name>.map` from `allMaps` but NOT from the pool lists.** The path is asymmetric: `allMaps` is a name-find lookup used by `rigMapName`, while the pool lists are random-roll lookups. They are independent and need both edits if the map was in both.
- **Forgetting to grep for other references.** `grep -rn "<Name>" server/src/` after the edit. Stale references typically lurk in: comments, KDoc on the map (if added recently), and any custom test assertions. The negative-path assertion in MapResourceRegistryTest is the intentional reference; everything else is residue.
- **Touching `us-america.zip`, `demo-map-pack.zip`, or `mapEditor/src/.../test-map*.zip`** unless the user explicitly asks. Out of scope per "The Iron Rule" above.

## Worked Example (2026-07-06 — fixedUSamerica.map removal)

> The map was deemed a strategic gameplay failure ("Use WMDs and sweep every tile every turn" — degenerate into RNG race, no player-player clash, boring for human play). User chose server-only removal; lobby preview kept as-is.

1. **Drop the file:** `rm server/src/main/resources/maps/fixedUSamerica.map` (1.8 MB).
2. **Edit `GameInit.kt`** — 4 references removed:
   - Comment at line 115: `// 2-player maps: fixedUSamerica, San_Martello` → `// 2-player maps: San_Martello`
   - `allMaps = listOf(...)` at line 123: removed the entry
   - Comment at line 156: `// Randomly pick one of the 2-player maps (fixedUSamerica, San_Martello, Arctica)` → `(San_Martello, Arctica)`
   - `twoPlayerMaps = listOf(...)` at line 158: removed the entry
3. **`allMaps` side-fix:** noticed Europa + Arctica were missing from the find-list (pre-existing bug from prior turns' installs). Added both while in the area. The `allMaps` block now reads:
   ```kotlin
   val allMaps = listOf(
       "maps/San_Martello.map",
       "maps/IO-map.map",
       "maps/Laurasiagondwana.map",
       "maps/jupiter.map",
       "maps/Europa.map",
       "maps/Arctica.map",
       "maps/StartMap.map"
   )
   ```
4. **Negative-path pin** in `MapResourceRegistryTest.kt`:
   ```kotlin
   assertTrue(
       maps.none { it.equals("maps/fixedUSamerica.map", ignoreCase = true) },
       "Expected maps/fixedUSamerica.map to be ABSENT (removed 2026-07-06: strategy degenerates " +
           "to WMD-sweep; the map is no longer fun for human play). Got $maps"
   )
   ```
5. **`MapSelectionService.kt` untouched** — `excludedRandomPoolPaths` is for installed-but-excluded maps, not for removed maps. The file's absence on disk means it can't roll via Path 4 anyway.
6. **Canonical Gradle run:**
   ```
   ./gradlew :server:test --tests "org.ttt.autogenesis.server.maps.MapResourceRegistryTest" \
       --console=plain --offline --rerun-tasks
   BUILD SUCCESSFUL in 1m 7s  (26 tasks executed)
   ```
   `MapResourceRegistryTest.xml` showed `tests="1" failures="0" errors="0"` with fresh timestamp.

## Outstanding after this removal

- **`kvisionApp/src/jsMain/resources/maps/us-america.zip`** still on disk per user choice. Lobby preview will surface the map; selecting it returns a server-side error (no `maps/fixedUSamerica.map` resource). Future patch opportunity to either remove the bundle or add a server-side "map not available" rejection RPC for known-removed maps.
- **2-player pool size:** now exactly 2 entries (San_Martello, Arctica). If both fail to load, the random fallback pulls from all 7 bundled maps (excluding tutorial) — 2-player games could end up on 4-player-shaped maps. Same behavior as before the removal (the pool used to be 3 entries but the fallback has always been 7 maps); the change just makes the fallback slightly more likely to fire. Flag as a future tightening if user wants 2-player-only map filtering on the fallback.
- **`allMaps` find-list drift hazard:** the allMaps list (lines 122-129) is a sibling-of-the-pools list that requires hand-sync. Each new install / removal should audit it. As of 2026-07-06 the list is in sync with the pool lists — but if a future session adds a map to a pool without also adding it here, `--map=<NewMap>` will silently fall through.

## Why pairing this with `scripts/verify-map-removal.py` matters

The 4-site purge is structurally simple but the **interaction** is what makes verification: a typo in `allMaps` or a stale comment in the `twoPlayerMaps` block leaves the codebase in a half-removed state. The source-tree verifier catches the cheap mistakes (file present, list contains the entry, comment still mentions the name, no negative-pin) in 50ms. The Gradle test confirms the runtime is consistent. Neither alone is sufficient — same principle as the install/exclusion recipes.
