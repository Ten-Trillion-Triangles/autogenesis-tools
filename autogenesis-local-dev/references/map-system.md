# Autogenesis Map System

## MapPack Format

A **map pack** is a ZIP file containing exactly two entries:

```
mappack.map (renamed .zip)
├── map.json       — serialized map metadata
└── <image>       — PNG or JPEG background map image
```

**`map.json` structure:**
```json
{
  "imageName": "map.png",
  "mapData": {
    "worldName": "The World",
    "storyScenario": "Optional scenario text",
    "pins": [
      {
        "pinId": "pin-uuid",
        "territory": { /* Territory data */ }
      }
    ],
    "connections": [
      { "fromPinId": "...", "toPinId": "..." }
    ]
  }
}
```

**`Territory` fields in `pins`:**
- `name`, `xPos`, `yPos`, `type`, `description`, `pointValue`
- `northObstacleType`, `southObstacleType` (border terrain)
- `northBorders`, `southBorders`, `eastBorders`, `westBorders`, `northEastBorders`, `northWestBorders`, `southEastBorders`, `southWestBorders` — populated by `reconstructBorders()` at load time

**Border reconstruction:** On load, `reconstructBorders()` in `MapPack.kt` iterates all connections and uses `atan2(dy, dx)` to determine compass direction, then populates bidirectional border lists between adjacent territories.

---

## Where Maps Live

### Packaged maps (shipped with server)

**Location:** `server/src/main/resources/maps/`

Files here are classpath resources. `MapResourceRegistry.listPackagedMaps()` scans the classpath for everything under `maps/` (works both in IDE and inside the packaged JAR).

**Current maps:**
```
server/src/main/resources/maps/
├── Europa.map             (3-4 players, 75 pins / 442 conns, all-Underwater theme)
├── IO-map.map             (3-4 players, 94 pins / 446 conns)
├── Laurasiagondwana.map   (3-4 players, 90 pins / 380 conns, "full" schema)
├── San_Martello.map       (fallback random pool, 49 pins / 242 conns)
├── fixedUSamerica.map     (fallback random pool, 47 pins / 246 conns)
└── jupiter.map            (3-4 players, 87 pins / 696 conns, "full" schema)
```

Maps are auto-discovered on next server start; no registration needed.

Two **schema variants** ship today (verified 2026-07-06 against all six .map files):

| Variant | Maps | `territory.size` | `territory.resource` | `territory.adjacentTerritoryNames` |
|---|---|---|---|---|
| "full" | jupiter, Laurasiagondwana, Europa | yes | yes | yes |
| "skeleton" | IO-map, San_Martello, fixedUSamerica | **no** | **no** | **no** |

`mapData.connections[]` (with `fromPinId`/`toPinId`) is **present in all six** — that's the load-bearing field. Adding a new map in either schema variant is tolerated, since the skeleton maps already ship. See `references/add-new-map-pack.md` for install + verify procedure.

### Uploaded maps (runtime-only, not persisted)

**Location:** In-memory only — `UploadedMapRepository` object in the JVM.

Players can upload a `.map` pack via the `server.uploadMapPack` RPC. The bytes are stored in a `LinkedHashMap` keyed by a random UUID. This is **not persisted** — maps disappear on server restart.

---

## How Maps Are Loaded

### Server init chain (`GameInit.kt`)

```
GameInit.configureSession()
  │
  ├─ player-count → specific map or random pool
  │    2 players → "maps/San_Martello.map" or "maps/fixedUSamerica.map" (one is picked)
  │    3, 4 players → random pick from
  │                    listOf("maps/IO-map.map",
  │                           "maps/Laurasiagondwana.map",
  │                           "maps/jupiter.map",
  │                           "maps/Europa.map")
  │    else → null (falls through to random)
  │
  ├─ if specific map loaded → WorldManager.loadMapFromResources(path)
  │
  ├─ else: MapSelectionService.loadRandomMapPack()
  │         ├─ packaged: MapResourceRegistry.listPackagedMaps()
  │         └─ uploaded: UploadedMapRepository.listUploadedMaps()
  │         random pick → WorldManager.loadMapFromPack(bytes)
  │
  └─ else fallback → WorldManager.loadMapFromResources("maps/StartMap.map")
```

### Core loading (`WorldManager.kt`)

```kotlin
// From classpath resource
suspend fun loadMapFromResources(resourcePath: String) {
    val bytes = contextClassLoader.getResourceAsStream(path).readBytes()
    loadMapFromPack(bytes, "resource:$path")
}

// From anywhere (resource, upload, file)
suspend fun loadMapFromPack(packBytes: ByteArray, source: String) {
    worldMutex.withLock {
        val newWorld = structs.loadWorldFromMapPack(packBytes)
        world = newWorld
        activeMapPackBytes = packBytes
        activeMapPackName = source
    }
}
```

### Shared parsing (`sharedModel/src/commonMain/kotlin/structs/MapPack.kt`)

```kotlin
suspend fun loadWorldFromMapPack(packBytes: ByteArray): World {
    val unpacked = MapPackManager.unpack(packBytes)  // unzip
    val mapData = unpacked.mapData

    val territories = mapData.pins.map { it.territory }.toMutableList()
    reconstructBorders(mapData)          // populate Border lists from connections
    territories.forEach { it.setTerritoryNamesForLlm() }
    initializeAllTerritoryThreats(territories)

    return World(name=mapData.worldName, storyScenario=mapData.storyScenario,
                 mapTiles=territories)
}
```

---

## Client Loading (Browser/UI)

### MapViewer (`kvisionApp/src/jsMain/kotlin/ui/MapViewer.kt`)

```kotlin
suspend fun loadMapPack(packBytes: ByteArray) {
    val unpacked = MapPackManager.unpack(packBytes)
    // Set background image
    val imageUrl = ImageLoader.getInstance().fromBytes(unpacked.imageBytes)
    // Draw territory pins/icons
    unpacked.mapData.pins.forEach { pin ->
        addTerritoryPin(pin.territory, pin.pinId)
    }
}
```

Receives bytes via RPC notification `ui.loadMapPack` from the server after a map upload or game start.

### Map editor (`mapEditor/`)

- **"Export Pack"** → `MapPackManager.pack()` → browser downloads `.map` file
- **"Load Pack"** → file picker → `MapPackManager.unpack()` → `canvas.loadFromPack(unpacked)`

---

## Installing a New Map

The install + wire-to-pool procedure is non-trivial enough that it lives in
`references/add-new-map-pack.md`. Key sub-procedures there:

- Schema verification: zip integrity, `mapData.pins[]` + `mapData.connections[]` shape
- Player-count archetype fingerprint (pin/connection count vs. existing 3-4 player maps)
- Pitfall: the bundled ships have TWO territory schema variants (full vs skeleton); either works
- Wire it into `GameInit.kt` 3-4 player pool literal at lines 171-177
- Pitfall: a path mismatch in the pool literal fails silently (fallback path runs)
- Re-runnable verifier: `scripts/verify-map-pack.py <map_file>` returns a fingerprint + pass/fail

### For server to auto-discover it (minimum-viable, no wire-up)

Drop the `.map` (ZIP) file into:

```
server/src/main/resources/maps/<name>.map
```

`MapResourceRegistry` finds it automatically on next server start. Without a
`GameInit.kt` edit, it lands in the **random-fallback pool only** (alongside
San_Martello and fixedUSamerica). It's reachable, just not first-class.

### For runtime upload

Send via `server.uploadMapPack` RPC, stored in-memory in `UploadedMapRepository`,
broadcast via `ui.loadMapPack` notification. Useful for custom maps that shouldn't ship.

## Exclusion mechanisms (tutorial / guided-walkthrough reserved maps)

Some `.map` files need to be **discoverable by deterministic-name loaders** but **invisible to random matchmaking** — guided tutorials, single-player walkthroughs, benchmark scenes. The complete exclusion surface area has 4 paths the agent must close:

| # | Path | File | Exclusion site |
|---|---|---|---|
| 1 | 2-player default roll | `GameInit.kt:153-162` | omit from `twoPlayerMaps` literal |
| 2 | 3-4 player default roll | `GameInit.kt:171-177` | omit from `threeFourPlayerMaps` literal |
| 3 | CLI rigged map (`--map=<name>`) | `GameInit.kt:122-129` | omit from `allMaps` literal |
| 4 | Random fallback | `MapSelectionService.kt:25-29` | add to `excludedRandomPoolPaths` set + confirm `.filterNot` at line 36-37 |

**Without Path 4**, the reservation is fragile — 12.5% per fallback fire (currently 1/8 installed maps). The 1000-roll JUnit test in `MapSelectionServiceTest.pickRandomDescriptor_excludesTutorialMap_butLoadBytesByNameStillResolvesIt` is the canonical gate. Companion source-tree verifier: `scripts/verify-map-exclusion.py <MapName>` — runs in 50ms, checks all 4 sites against disk state without Gradle.

The reserved map IS loadable by name via `MapSelectionService.loadBytesByName("maps/<name>.map")` — that gives future tutorial RPCs a deterministic-name contract. Add JSON metadata (`mapData.isTutorial: true`) on re-export only if dispatcher-side differentiation is wanted; default is the deterministic-name convention.

Full worked example (tutorial.map install, 2026-07-06) and the install procedure: see `references/add-new-map-pack.md` "Non-matchmaking install (tutorial / guided-walkthrough reserved map)".

---

## Key Files

| File | Role |
|------|------|
| `sharedModel/src/commonMain/kotlin/structs/MapPack.kt` | MapPack data classes, `loadWorldFromMapPack()`, `reconstructBorders()` |
| `sharedModel/src/jvmMain/kotlin/structs/MapPackManager.kt` | JVM ZIP pack/unpack (ZipInputStream/ZipOutputStream) |
| `sharedModel/src/jsMain/kotlin/structs/MapPackManager.kt` | JS ZIP pack/unpack (JSZip) |
| `server/src/main/kotlin/gameState/WorldManager.kt` | `loadMapFromPack()`, `loadMapFromResources()` |
| `server/src/main/kotlin/gameInit/GameInit.kt` | Player-count → map path mapping, init chain |
| `server/src/main/kotlin/gameInit/MapSelectionService.kt` | Random map selection across packaged + uploaded |
| `server/src/main/kotlin/org/ttt/autogenesis/server/maps/MapResourceRegistry.kt` | Classpath scan for `maps/` resources |
| `server/src/main/kotlin/org/ttt/autogenesis/server/maps/UploadedMapRepository.kt` | In-memory uploaded map storage |
| `server/src/main/kotlin/MapRpcHandlers.kt` | `server.uploadMapPack` RPC handler |
| `kvisionApp/src/jsMain/kotlin/ui/MapViewer.kt` | Client-side map rendering |
| `mapEditor/src/jsMain/kotlin/ui/TopBar.kt` | Map editor save/load/export UI |
| `mapEditor/src/jsMain/kotlin/ui/MapCanvas.kt` | `saveMapData()`, `loadMapData()` |
