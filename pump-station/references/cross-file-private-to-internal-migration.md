# Cross-file field mutation: `internal var` vs `private var` + accessor (2026-07-24)

## The pattern

When a state field on class `A` must be MUTATED from a helper function in a sibling file (class `B`'s extension function or top-level function in another file in the same module), the cleanest shape is:

```kotlin
// In class A's body (e.g. PumpStation.kt)
internal var myCounter: Int = 0

// In class B's extension function (e.g. PumpStationLoop.kt)
fun PumpStation.someHelper() {
    myCounter += 1   // ← direct write works; same module
}
```

`internal` (not `private`) is required because the writer is in a different file. `var` (not `val`) is required because the writer needs to mutate. The `internal val accessor + private backing field + setter helper` pattern is the alternative, but it's 3-4 lines of boilerplate per field that doesn't pay for itself when there's a real cross-file mutation need.

## When to use the accessor pattern instead

The accessor pattern is the right shape when:
- The field is read from outside the class but only WRITTEN from within the class (the `consecutivePathCount` / `consecutivePathCountInternal` pattern at `PumpStation.kt:2549-2550`).
- The field is conceptually read-only from outside the class (e.g. exposing internal state for observability or test assertion).
- Cross-module readers are possible and the field should NOT be writable from another module.

When the field needs cross-file MUTATION within the same module, `internal var` is the simpler shape.

## Worked example — Bug B fix (2026-07-24)

The `maxConsecutiveUnknownPaths` counter needs to increment inside `runPathFlow` (a `PumpStationLoop.kt` extension function, not a `PumpStation` member function). First iteration of the fix used the accessor pattern:

```kotlin
// First iteration (commit 06eb0935, broken):
private var consecutiveUnknownPathCount: Int = 0
internal val consecutiveUnknownPathCountInternal: Int
    get() = consecutiveUnknownPathCount
```

The test class then tried `station.consecutiveUnknownPathCountInternal = 5` and hit Kotlin's "'val' cannot be reassigned" compile error. The accessor is a getter only — there's no setter by design. The fix could have been to add a setter helper method (`fun resetConsecutiveUnknownPathCount() { consecutiveUnknownPathCount = 0 }`), but that's 3 lines of boilerplate for a 2-line operation.

Final shape (commit `e1aa3dc4`):

```kotlin
// PumpStation.kt:
internal var consecutiveUnknownPathCount: Int = 0

// PumpStationLoop.kt:
consecutiveUnknownPathCount += 1      // direct write works
consecutiveUnknownPathCount = 0       // direct reset works
```

The `internal` keyword is load-bearing — without it, `PumpStationLoop.kt` can't write the field. The `var` keyword is load-bearing — without it, the field is read-only. Both are required for this pattern.

## The accessor pattern with setter helper (alternative shape)

If the field should be `private` for encapsulation reasons and cross-file mutation is still required, the canonical alternative is a setter helper method:

```kotlin
private var myCounter: Int = 0
internal val myCounterInternal: Int get() = myCounter
internal fun bumpMyCounter() { myCounter += 1 }
internal fun resetMyCounter() { myCounter = 0 }
```

This pattern is 3-4 lines vs. `internal var myCounter: Int = 0` at 1 line, but it preserves the encapsulation boundary (external callers can only read or use the named operations, not write arbitrary values). Use it when the field's mutation should be a domain operation (e.g. `bumpGoalFailCount()`, `resetStreakCounter()`) rather than an arbitrary write.

For the Bug B counter, `internal var` is the right shape because:
- The field is a streak counter with no semantic operation; the helpers would be trivial (`bump()` = `+= 1`, `reset()` = `= 0`).
- The "wrong" write is structurally impossible — the writer is `runPathFlow` itself, not external code.
- The 1-line shape makes the change easier to review and reason about.

## Test-side accessor pattern (different concern)

Tests that READ state from a test class use the `*Internal` accessor pattern:

```kotlin
// In test class
val counterBefore = station.consecutiveUnknownPathCountInternal
val limit = station.maxConsecutiveUnknownPathsInternal
```

This is read-only — the test cannot write. The accessor pattern is correct for read access. The accessor is `internal val` (not `private`) so the test class in the same module can read.

The accessor and the `internal var` patterns serve different purposes:
- **Accessor** (`internal val`) for read access from outside the class.
- **`internal var`** for read+write access from outside the class.

They can coexist: the field is `internal var` for direct access, and you can ALSO expose a `*Internal` `val` getter for read-only test assertions if you want a stable read surface. For simple counters, direct `internal var` access is enough — tests read via `station.consecutiveUnknownPathCount` and write via `station.consecutiveUnknownPathCount = 0` from any sibling code.

## When the pattern does NOT apply

- **Different modules**: if the writer is in a different Gradle module, `internal` won't work. Use a public setter or a public `fun setXxx(value)` instead. (For TPipe, every `Pipeline/*.kt` file is in the same module, so `internal` works. For multi-module projects, this needs more thought.)
- **The field is conceptually a `val`**: if no caller should mutate, keep it `val` (with the `private` keyword if it's truly internal-only). The `internal var` shape is for fields that genuinely need to mutate.
- **The field is on a `data class`**: data class auto-generates a `copy()` method that won't include body-level `var` properties. Use the primary constructor parameter list for case where the data class needs to track mutable state — see the `MultimodalContent.metadata` body-level-`var` trap in the `pump-station` SKILL.md (which has a different shape but similar concern).
- **Concurrency-safe mutation is required**: `internal var` is plain unsynchronized. If the writer can race with itself (multiple coroutines mutating the same field), the right shape is `AtomicInteger` or a `Mutex`-guarded write. The `consecutiveUnknownPathCount` in the Bug B fix is single-threaded per harness (the dispatch loop is sequential), so plain `var` is correct — but document the concurrency contract in the KDoc so a future multi-threaded call site is forced to add synchronization.

## Generalization

This pattern applies across the entire TPipe codebase, not just `PumpStation`. Every container that has cross-file state (Manifold's `workerRegistry`, Junction's `participantMap`, DistributionGrid's `nodeTable`) likely has a similar shape: state on one class, mutation from another file. The `internal var` pattern is the right default when the mutation is structural (counter increments, flag toggles, map updates). The accessor pattern is the right default when the mutation is semantic and the helper methods are non-trivial.

If you're tempted to add a `private var myCounter` plus a `fun bumpMyCounter()` helper plus an `internal val myCounterInternal` accessor, ask first: is the helper doing anything more than `counter += 1` or `counter = 0`? If not, prefer the 1-line `internal var` shape.
