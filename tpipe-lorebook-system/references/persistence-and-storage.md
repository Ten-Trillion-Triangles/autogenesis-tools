# Lorebook Persistence and Storage in ContextBank

Source: `src/main/kotlin/Context/ContextBank.kt` (1,737 LOC) plus `src/main/kotlin/Context/MemoryPersistence.kt` and `src/main/kotlin/Context/StorageMode.kt`.

## Storage modes - the 5-option enum

Defined in `StorageMode.kt`:

```kotlin
enum class StorageMode {
    MEMORY_ONLY,
    MEMORY_AND_DISK,
    DISK_ONLY,
    DISK_WITH_CACHE,
    REMOTE
}
```

Each maps to a different `loadContextWindowForKeyLocked` branch (`ContextBank.kt:187-200`):

| Mode | On read | On write |
|------|---------|----------|
| `MEMORY_ONLY` | in-memory only; no disk | in-memory only; no disk |
| `MEMORY_AND_DISK` | load from disk if not in memory, populate memory | write to memory and disk |
| `DISK_ONLY` | load from disk; do NOT populate memory | write directly to disk |
| `DISK_WITH_CACHE` | load from disk; populate memory | write to memory and disk |
| `REMOTE` | remote only; not handled here | remote only; not handled here |

Note: `DISK_ONLY` and `DISK_WITH_CACHE` differ ONLY in cache behavior on read. `MEMORY_ONLY` and `MEMORY_AND_DISK` differ ONLY in persistence behavior on write.

## Disk layout

`${TPipeConfig.getLorebookDir()}/${pageKey}.bank` - one file per page key.

The entire `ContextWindow` (including `loreBookKeys`, `contextElements`, `converseHistory`, `metaData`, `version`) is serialized as JSON via `Util.serialize(...)` and stored.

**There's no lorebook-level file. There's no partial disk write.** The .bank file IS the page. If you write a 10MB lorebook, the .bank file is at least 10MB.

Path is configurable via `TPipeConfig.getLorebookDir()` - defaults to a project-local directory. Look for `getLorebookDir()` in `src/main/kotlin/Config/TPipeConfig.kt` for the exact default.

## Atomic write

`MemoryPersistence.writeMemoryFile(path, contents)` writes atomically - typically via tempfile-rename pattern. The `.bank` extension is conventional; the serialization uses kotlinx.serialization JSON.

`MemoryPersistence.readMemoryFile(path)` reads and returns the raw string. Caller deserializes via `deserialize<ContextWindow>(...)`.

`MemoryPersistence.deleteMemoryFile(path)` deletes if exists.

## Page mutex semantics

`ContextBank.getPageMutex(key): Mutex` - one `kotlinx.coroutines.sync.Mutex` per page key, stored internally.

`withContextWindowReferenceSuspend(key, mode, skipRemote, block)` - the canonical entry point:

```kotlin
suspend fun <T> withContextWindowReferenceSuspend(
    key: String,
    mode: StorageMode = StorageMode.MEMORY_AND_DISK,
    skipRemote: Boolean = false,
    block: (ContextWindow) -> T
): T
```

1. Acquires `getPageMutex(key).lock()`.
2. Loads the window via `loadContextWindowForKeyLocked(key, mode)`.
3. Invokes `block(window)`.
4. Writes back via `windowToWriteBack` after the block (mode-dependent).
5. Releases the lock.

**Why per-page mutex instead of one global lock:** different pages can be edited concurrently. The mutex only serializes access to one page at a time. Reading the same page from one coroutine while another holds the lock will block until the block completes.

**Skip-remote flag:** when remote-backed, the lock semantics change (remote sync happens AFTER the local mutex releases, to avoid holding local locks across network calls). `skipRemote = true` forces local-only behavior.

## Page key registry

`ContextBank.getPageKeysSuspend(skipRemote)` returns `List<String>` of all known page keys.

Source of truth (MEMORY mode): in-memory `bank.keySet()`.
Source of truth (DISK mode): `getLorebookDir()` directory listing (`*.bank`).
Source of truth (REMOTE): `MemoryClient.getPageKeys()`.

The function dispatches based on each page key's `storageMetadata` (`StorageMode`).

## Lorebook-specific persistence behavior

**There is no lorebook-level persistence API.** All lorebook persistence happens at the page level.

To persist a lorebook entry:
1. Acquire `getPageMutex(pageKey)`.
2. Load the `ContextWindow` (creates if absent).
3. Modify `window.loreBookKeys[key] = newEntry` (or call `addLoreBookEntry`).
4. The `withContextWindowReferenceSuspend` writeback serializes the whole window.

To persist a MiniBank-multi-page composition:
1. Iterate every `MiniBank.contextMap` entry.
2. For each, call `withContextWindowReferenceSuspend(pageKey) { window -> ... }` to apply per-page diffs.
3. Cross-page persistence is NOT atomic.

To persist a lorebook agent's output:
- PumpStation does this via `applyTypedLorebookUpdates` (`PumpStationLoop.kt:1416`) which mutates the running `ContextWindow` and relies on a downstream writeback (or the per-page mutex if called inside one).

## Migration between modes

Changing a page key's `StorageMode` mid-session does NOT migrate existing data automatically. You must:

1. Read existing data via the old mode.
2. Write it via the new mode.
3. Delete the old-format file if applicable.

`ContextBank.changeStorageMode(key, newMode)` (if it exists) handles this. If not, manual orchestration is needed.

## REMOTE mode

`StorageMode.REMOTE` delegates to `MemoryServer` (`src/main/kotlin/Context/MemoryServer.kt`) via `MemoryClient`.

**This mode has NOTHING to do with disk.** The lorebook dir is unused. `bank[]` is unused. State lives entirely on a remote TPipe instance reachable via `MemoryClient`.

**To run a remote memory server:** start a second TPipe instance with `--remote-memory` flag (`Application.kt` mode switch). Connect via `MemoryClient` configured with the remote URL.

`MemoryRemoteException` is thrown on remote failures. The lock trio uses `requireSuccess` / `requireValue` helpers that wrap remote results.

## `ContextLock` metadata writes

When `addLockSuspend` runs, it iterates affected pages and writes `metaData["isLocked"] = lockState` to each via `withContextWindowReferenceSuspend`. **This persistence is essential** - if a process restarts, the in-memory `locks` map is empty, but the persisted `metaData["isLocked"]` can be detected at boot.

There's a separate `populateContextLockFromMetadataSuspend` (or similar) that scans persisted windows and recreates `locks` entries from `metaData["isLocked"] = true`. Check `ContextBank.kt` or `ContextLock.kt` for the exact boot-time hook.

## `storageMetadata` per page key

Each page key has a `StorageMetadata` record tracking: storage mode, last-accessed timestamp, access count. Used to:
- Decide cache eviction policy (`DISK_WITH_CACHE` mode).
- Drive the page-key enumeration under varying storage conditions.

See `src/main/kotlin/Context/StorageMetadata.kt`.

## Common mistakes

### "I'll save the lorebook directly"
No API exists to write a single lorebook entry to disk. You MUST write through the `ContextWindow`. The most common mistake is holding an in-memory lorebook change and expecting it to persist via `addLoreBookEntry` alone - that updates the in-memory map but NOT the disk file. Wrap in `withContextWindowReferenceSuspend` or call `ContextBank.writeBack(key)` (if it exists).

### "Two concurrent lorebook writes are safe because loreBookKeys is a HashMap"
WRONG. `HashMap` is not thread-safe; concurrent reads + writes can deadlock or corrupt. Use `getPageMutex(key).withLock` around any read-modify-write.

### "I'll change `loreBookKeys` from a non-page context"
If the `ContextWindow` came from `bank[key]` without holding the mutex, your changes can be silently lost when another writer flushes. **Always write through `withContextWindowReferenceSuspend`.**

### "Remote is faster than local disk"
No - remote is SLOWER (network round-trip) and adds a single point of failure. Use remote only when the data must be shared across processes or hosts.

### "I want per-lorebook locks"
You can lock a lorebook key globally. You CANNOT lock an individual lorebook entry (a single LoreBook's value field) - the lock granularity is `KeyBundle.keys: List<String>`. If you have two entries with the same key (rare; possible after a merge), they're treated as one lockable unit.

## See also

- `../SKILL.md` ContextBank persistence and ContextLock sections.
- `pump-station/SKILL.md` contract #7 for how lorebook persistence integrates with PumpStation's lorebookAgent.
- `tpipe-json-serialization/SKILL.md` for serialization edge cases (defaults, malformed JSON repair) that affect .bank file round-trips.
