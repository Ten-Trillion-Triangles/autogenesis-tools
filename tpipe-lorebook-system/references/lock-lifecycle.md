# ContextLock Lifecycle and the Trio Pattern

Source: `src/main/kotlin/Context/ContextLock.kt` (534 LOC). Singleton `object ContextLock` with `ConcurrentHashMap<String, KeyBundle>` storage and `Mutex` for lifecycle safety.

## KeyBundle - the storage unit

```kotlin
data class KeyBundle(
    var keys: MutableList<String> = mutableListOf(),
    var pages: MutableList<String> = mutableListOf(),
    var isGlobal: Boolean = false,
    var isLocked: Boolean = false,
    var isPageKey: Boolean = false,
    var passthroughFunction: (() -> Boolean)? = null
)
```

**Fields:**
- `keys` - lorebook keys captured at add-lock time. Filtered by `findLoreBookEntry` lookup per page.
- `pages` - pages captured at add-lock time. Used to drive metadata writes.
- `isGlobal` - true when `pageKeys` was empty at add time (lock applies to all pages).
- `isLocked` - whether the lock is currently active. Flipped by `lockKeyBundle`/`unlockKeyBundle`.
- `isPageKey` - true if the lock targets a page (not a lorebook key); affects which choke points engage.
- `passthroughFunction` - sync `() -> Boolean` callback. Returning `true` admits the key despite `isLocked=true`.

## The trio pattern: sync / `_Suspend` / `_WithMutex`

Every public API has THREE variants. This is by design and is the dominant contract in this file.

| Pattern | Purpose | When to use |
|---------|---------|-------------|
| `addLock(args, skipRemote=false)` | blocking compatibility | from sync code with no coroutine context |
| `addLockSuspend(args, skipRemote=false)` | coroutine-native | from inside `suspend fun` |
| `addLockWithMutex(args, skipRemote=false)` | coroutine + `lockMutex` held | from concurrent processes that may race with other lock lifecycle mutations |

The trio applies to: `addLock*`, `removeLock*`, `lockKeyBundle*`, `unlockKeyBundle*`. Lookup methods (`isKeyLocked`, `isPageLocked`, `getKeyBundle`) only have sync / `_Suspend` because they don't mutate.

## `addLockSuspend` - the resolution order

1. If NOT `skipRemote` AND (`remoteMemoryEnabled` OR `useRemoteMemoryGlobally`) -> POST to `MemoryClient.addLock(LockRequest(key, pageKeys, isPageKey, lockState))`. Throws via `requireSuccess("add remote lock '$key'")` on failure.
2. Determine affected pages:
   - empty `pageKeys` arg -> `ContextBank.getPageKeysSuspend(skipRemote = true)` (all known pages).
   - else -> `pageKeys.split(",").map { trim }.filter { isNotEmpty }` (CSV parsing).
3. For each affected page (with `skipRemote = true` on the recursive calls):
   - Set `metaData["isLocked"] = lockState` via `ContextBank.withContextWindowReferenceSuspend`.
   - Look up `findLoreBookEntry(key)` on that page - if found, add the lorebook key string to `keys`.
4. If `isPageKey`: skip the lorebook lookup, just record the pages.
5. Lowercase-normalize the key (`normalizeKey`) and store the `KeyBundle` in `locks`.

## `removeLockSuspend`

Resolution order:
1. If NOT `skipRemote` AND remote enabled -> DELETE via `MemoryClient.removeLock(key)`.
   - `MemoryOperationResult.Failure(notFound)` is **silently tolerated** (remove-on-missing is a no-op).
   - Other failures throw via `MemoryRemoteException`.
2. Remove from local map: `locks.remove(normalizeKey(key))?`.
3. If `bundle.isPageKey` -> return (page lock cleanup is below; skip).
4. Compute pages to clean:
   - if `bundle.pages.isNotEmpty()` -> use them.
   - else if `bundle.isGlobal` -> `ContextBank.getPageKeysSuspend(skipRemote = true).toSet()`.
   - else -> `parsePageKeys(key).toSet()` (rare fallback).
5. For each page, `ContextBank.withContextWindowReferenceSuspend(page, skipRemote = true) { it.metaData.remove("isLocked") }`.

## Lock state toggling - `lockKeyBundle` / `unlockKeyBundle`

These are STATE flips on an EXISTING bundle. They do not add or remove.

`lockKeyBundleSuspend(key)`:
1. Optional remote update via `MemoryClient.updateLockState(key, true)`.
2. If remote returns `notFound` AND local bundle exists -> recreate the remote lock with the current bundle's pages.
3. Other remote failures throw.
4. Get the local `bundle`. Flip `bundle.isLocked = true`.
5. If `bundle.isPageKey` -> return.
6. Compute pages (same resolution order as remove).
7. For each page, set `metaData["isLocked"] = true`.

`unlockKeyBundleSuspend(key)` is the inverse (state=false).

## Lookup family

`isKeyLocked(key, skipRemote=false)`:
1. `locks[normalizeKey(key)]?.isLocked ?: false` -> local answer.
2. If `false` AND not skipRemote AND remote enabled -> `MemoryClient.isKeyLocked(key).requireValue(...)` -> remote answer.
3. Return.

`isKeyLockedSuspend(key, skipRemote=false)`:
- Same as above but using `requireValue` which `throws` on non-success. Use only when remote MUST be consulted.

`isPageLocked(pageKey, skipRemote=false)`:
- Returns `locks[normalizeKey(pageKey)]?.isPageKey == true && bundle.isLocked`.

`isPageLockedSuspend(pageKey, skipRemote=false)`:
- Same as `isKeyLockedSuspend` but for pages.

## `getLockedKeysForContext(window, pageKey, skipRemote=false)`

Synchronously returns `Set<String>` of lorebook keys that are currently locked AND applicable to the given context window.

Filter: `bundle.isLocked && !bundle.isPageKey && (bundle.isGlobal || (pageKey != null && bundle.pages.contains(pageKey)))`.

Used by `ContextWindow.getLockedKeys()` (line 2271) and indirectly by the lock-aware selection stages.

## `passthroughFunction` - the bypass mechanism

A lock bundle can attach a `() -> Boolean` callback. When the lock is consulted at selection time:
1. If `bundle.passthroughFunction != null` -> invoke it.
2. Return its boolean (true = admit, false = deny).
3. Exception -> fall back to `!bundle.isLocked` (honor the lock).

This lets a runtime decision override a static lock. Example use cases:
- "always admit `key=safetyOverride` unless the safety module says no" - register `passthroughFunction = { safetyModule.allowsLorebook(contextWindow) }`.
- "admit `key=adminOverride` for admin users" - register `passthroughFunction = { currentUser.isAdmin }`.

The function MUST be sync (not suspend) - it's called from sync selection paths. If you need async passthrough logic, you'd have to roll your own suspension point (suspend selection does NOT pass through passthrough differently).

## Choke points where locks engage in `ContextWindow`

Stage 4 candidate-triple filter (algorithm-step-4): `canSelectLoreBookKey(key)` is called.
Stage 1 `findMatchingLoreBookKeys`: ALSO calls `canSelectLoreBookKey` per hit.
Stage 6.5 `selectAndFillLoreBookContextSuspend` fill pass: ALSO calls `canSelectLoreBookKey` per candidate.

This means a locked key is filtered THREE times before it's definitively excluded. If you want a key to bypass, the lock bypass must succeed at all three choke points. The lock check is identical at all three (same function name), so passing at one passes at all.

## Remote vs local resolution

When `remoteMemoryEnabled = true` or `useRemoteMemoryGlobally = true`:
- `addLock*` mirrors to `MemoryClient.addLock(...)`.
- `removeLock*` mirrors to `MemoryClient.removeLock(...)` (tolerates `notFound`).
- `lockKeyBundle*` / `unlockKeyBundle*` mirror to `MemoryClient.updateLockState(...)`.
- `isKeyLockedSuspend` / `isPageLockedSuspend` consult `MemoryClient.isKeyLocked` / `isPageLocked` after the local check.

When `skipRemote = true`:
- All remote calls are skipped. Local-only resolution.
- Used by internal recursive calls (e.g. `addLockSuspend` calls `withContextWindowReferenceSuspend(skipRemote = true)` to avoid recursion).
- Tests use this to keep state local.

## Common patterns and errors

### Pattern: race-free bundling

```kotlin
// From a coroutine
lockMutex.withLock {
    ContextLock.addLockSuspend("fireball", "page1,page2", isPageKey = false)
}
```

The `lockMutex` prevents concurrent `addLock` / `removeLock` / `lockKeyBundle` / `unlockKeyBundle` from interleaving on the same bundle. Without it, two concurrent adders can produce inconsistent state.

### Error: `addLock` re-firing on already-locked bundle

`addLock` OVERWRITES any existing bundle under the same normalized key. There's no "merge" or "increment". If you call `addLock("fireball", "page1")` then `addLock("fireball", "page2")`, the second call replaces the first. `bundle.pages` now only contains "page2".

If you want to merge, call `addLockSuspend` with the union of `pageKeys` yourself.

### Error: `lockKeyBundle` on missing bundle silently succeeds

`applyLockStateSuspend` does `locks[normalizeKey(key)] ?: return` - if the bundle doesn't exist, it returns silently. This is a no-op, not an error. If you intend to lock a specific key, ensure `addLock` ran first.

### Error: page lock vs key lock confusion

`isPageKey = true` means "lock this page, not the lorebook key on it". When `true`, `keys` is empty (the discovery loop in `addLockSuspend` skips). `getLockedKeysForContext` ALSO filters out `isPageKey` bundles via `!bundle.isPageKey`. Setting it wrong means the lock either has no effect on selection or no effect on page-level locking.

### Error: `passthroughFunction` exceptions default to deny

```kotlin
bundle.passthroughFunction = { throw RuntimeException("test") }
// At selection: bundle.passthroughFunction?.invoke() -- throws
// Catch block: return !bundle.isLocked
```

If `bundle.isLocked = true`, the catch returns `false` -> the lock holds. If `bundle.isLocked = false`, the catch returns `true` -> no effect. **A buggy passthrough function effectively becomes a hard lock when `isLocked=true`.** Test your passthrough functions independently before registering them.

## See also

- `../SKILL.md` ContextLock section for the high-level summary.
- `pump-station/SKILL.md` contract #7 for how PumpStation's lorebookAgent produces keys that may then need locking.
