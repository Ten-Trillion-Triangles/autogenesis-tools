---
name: tpipe-context-pull-builder-repair
description: |
  Repair recipe for dead "pull from X" builders on `Pipe` and similar containers. A "pull" builder that flips a flag but has no execution-time read site is silent no-op vaporware. This skill captures the end-to-end fix workflow used on `pullPumpStationContext()`: TDD red-green against a real PumpStation ownership chain, deep-copy-before-merge rationale, the generic `P2PInterface.getContextWindowFromInterface()` / `getMiniBankFromInterface()` / `getNearestPumpStationParent()` traversal, the merge-order contract (global → pipeline → parent-pipe → PumpStation → pre-validation → truncation → injection), and the verification ritual. Load when a builder on `Pipe` (or any sibling that mirrors this pattern) is suspected to be silent, when fixing a documented merge-order contract, or when writing the test matrix for any context-pull builder.
version: 1.0.0
metadata:
  hermes:
    tags: [tpipe, pipe, context, pumpstation, pull-builder, repair, tdd, deep-copy, merge-order]
    related_skills: [tpipe-pipe-internals, software-development:interactive-plan, software-development:test-driven-development, software-development:verifying-code-changes]
---

# TPipe Context-Pull Builder Repair

## What this skill covers

The class of bug where a public `pipe.somePull()` builder exists, compiles, and is documented in KDoc but does nothing at runtime because `executeMultimodal` never reads the flag it sets. The user-facing symptom is "my context is not flowing" — usually framed around PumpStation, parent-pipe, pipeline, or global context.

## The pattern, in one breath

A "pull" builder is two things: a setter that flips a private flag, and a branch inside the execution flow that reads the flag and performs a merge. When the setter exists and the branch does not, the builder is silent. The fix is symmetric: find the merge site that was missed, wire the read with deep copies, and pin every behavior change with a focused test.

## Six-step fix workflow

### 1. Confirm the dead-builder diagnosis before patching

Run:

```bash
grep -nE 'readFrom[A-Z][a-zA-Z]*Context' src/main/kotlin/Pipe/Pipe.kt
```

Any pull flag that has no `if(readFromX)` consumer inside `executeMultimodal` is a dead builder. Cross-check with `git blame` to find the commit that introduced the setter — the commit that added the setter usually introduced the supporting infrastructure too (consumer-side accessor + concrete-class overrides). The patch is then: add the missing branch where the supporting infrastructure was already pointing.

### 2. Verify the supporting infrastructure exists before writing it

For `pullPumpStationContext()` the supporting code was already in place from commit `a84a91b8 expand p2p interface`:

- `P2PInterface.getNearestPumpStationParent()` — ancestry walker, `P2PInterface.kt:176`
- `P2PInterface.getContextWindowFromInterface()` — generic accessor, `P2PInterface.kt:145`
- `P2PInterface.getMiniBankFromInterface()` — generic accessor, `P2PInterface.kt:150`
- `PumpStation.getContextWindowFromInterface()` / `getMiniBankFromInterface()` overrides — `PumpStation.kt:2013`, `:2018`

If the supporting infrastructure does not exist, add it FIRST as a separate change. Skipping this step is how "parity work" expands into a refactor masquerading as a fix.

### 3. Pin the contract with a focused TDD matrix BEFORE editing production code

The seven-test matrix from the 2026-07-22 PumpStation bridge repair (`src/test/kotlin/Pipe/PipePumpStationContextTest.kt`) is the canonical shape. Reuse it for any sibling builder:

| Test | What it pins |
|---|---|
| Opt-in default (false) | Builder does not pull unless explicitly enabled |
| Opt-in default (true) | Builder pulls when enabled |
| `ContextWindow` pull | Single-page context window merges into `contextWindow` |
| `MiniBank` pull | Multi-page storage merges into `miniContextBank` |
| Merge order | New merge occurs AFTER existing context sources, BEFORE pre-validation |
| Missing ancestor | Builder safely no-ops when no qualifying parent exists |
| Deep-copy isolation | Pipe mutation/truncation does not mutate source-owned objects |

Run the matrix. Expect 3 REDs (pull, MiniBank, merge order). The other four already pass because the missing branch makes them trivial.

### 4. Wire the merge with deep copies and the existing policy flags

Patch shape, immediately after the previous merge block, matching the documented order:

```kotlin
if(readFromXContext)
{
    val sourceParent = getNearestXParent()
    sourceParent?.getContextWindowFromInterface()?.let { sourceContext ->
        contextWindow.merge(sourceContext.deepCopy(), emplaceLorebook, appendLoreBook, emplaceConverseHistory, emplaceConverseHistoryOnlyIfNull)
    }
    sourceParent?.getMiniBankFromInterface()?.let { sourceMiniBank ->
        miniContextBank.merge(sourceMiniBank.deepCopy(), emplaceLorebook, appendLoreBook, emplaceConverseHistory, emplaceConverseHistoryOnlyIfNull)
    }
}
```

Three properties are non-negotiable:

- **Deep-copy before merge.** Without it, the pipe's downstream truncation or pre-validation mutates source-owned memory by reference. The result is silently-correct locally and silently-broken on the next PumpStation turn — the worst class of bug to chase.
- **Reuse the existing policy flags.** `emplaceLorebook`, `appendLoreBook`, `emplaceConverseHistory`, `emplaceConverseHistoryOnlyIfNull` are the project's canonical merge knobs. Inventing a new flag for one builder splits the policy surface.
- **Use the generic interface, not a concrete cast.** `getNearestPumpStationParent()` returns `P2PInterface?` and the accessors are defined on `P2PInterface`. Do NOT cast to `PumpStation` — that would couple the pipe to one container type and break the generic surface that was created for this feature.

### 5. Run focused, then adjacent, then package

After the fix:

```bash
./gradlew :test --rerun-tasks --tests "<focused test class>" --tests "<adjacent regression>"
./gradlew :test --tests "com.TTT.Pipe.*"
```

The `--rerun-tasks` flag is mandatory when capturing fresh verification evidence; without it Gradle reports `UP-TO-DATE` and the system reminders treat that as no evidence.

### 6. Report ad-hoc verification, not suite green

The user's machine is the source of truth. State explicitly:

- which tests ran with `--rerun-tasks`;
- the captured exit status;
- which paths were touched in the working tree;
- what is NOT yet covered (full suite, unrelated modified files).

This is the compliance shape for verification reports. Do not claim "the suite is green" after running a focused subset.

## Recipe: how to know when the patch is correct

If the seven-test matrix passes, the merged-source flag chain is unchanged, and the working-tree diff is exactly one new branch plus a new test file, the patch is correct. Any of these are red flags: a comment that narrates the bug, a code-block that duplicates the parent-pipe merge, a write-back feature added "while I was at it," or a concrete-type cast where the interface would do.

## Pitfalls

### Deep-copy is mandatory, not optional

The single most likely mistake when wiring a context merge is to skip the `deepCopy()` because "we just read it." The pipe mutates its own `contextWindow` during truncation and pre-validation. If that mutation reaches back into the source's memory by reference, the source's state is corrupted for the next turn. The test that catches this is `importedContextDoesNotAliasSourceState` — write it, run it, do not delete it.

### Do not add a concrete-type cast

`pumpStation as PumpStation` is a trap. It compiles, and it works for the one container you tested, and it breaks every other `P2PInterface` that wants to expose a context window. The feature was built generically for a reason. Use the interface.

### Do not add write-back behavior "while you're there"

The documented contract for `pullPumpStationContext()` is one-way: pipe imports, does not write back. Adding write-back in the same patch expands scope, introduces shared-memory concerns, and breaks the test isolation guarantee. If write-back is wanted, it is a separate plan.

### Do not skip the merge-order test

`pipeline → parent-pipe → PumpStation → pre-validation` is the documented order. If a regression moves PumpStation import before pipeline context, the system silently re-orders memory precedence and operators will debug it for hours. The merge-order test is the one that pins this. Run it, keep it, do not "simplify" it.

### Do not narrate the bug in production code

Comments like `// bug fix for ticket X`, `// previously this flag was never read`, `// commit a84a91b8 left this disconnected` belong in the changelog or commit message, not in the source. Production code describes behavior; commit history describes history.

## Anti-pattern: "the test passes on first run"

A test that passes on first run after a production-code change is suspicious. Either (a) the test does not exercise the change, (b) the change was a no-op, or (c) the test was written to match the implementation rather than the contract. The TDD ritual is RED first — watch the test fail with the precise error that matches the defect — then GREEN. A first-run pass is a red flag, not a milestone.

## Verification artifact shape

After the patch:

- `/tmp/<feature>-red.txt` — focused test output before the production-code change, capturing the precise assertion failures that match the defect.
- `/tmp/<feature>-green.txt` — focused test output after the production-code change, capturing the same tests now passing.
- `/tmp/<feature>-verification.txt` — combined focused + adjacent + package output, captured with `--rerun-tasks`.

These artifacts are how the system reminder "workspace does not have fresh passing verification evidence" is satisfied. Without them, the work is unverified regardless of how confident the report sounds.

## Support files

- `references/repair-session-2026-07-22.md` — full transcript of the canonical repair: pre-flight RED output, post-fix GREEN output, the final patch verbatim, the three load-bearing design decisions (deep-copy, merge order, generic-interface traversal), and the captured verification artifacts.
- `scripts/verify-context-pull-builder.sh` — minimal verification script that runs the focused + adjacent test classes with `--rerun-tasks` so the system reminder treats the run as fresh evidence.

## Changelog

- **1.0.0 (2026-07-22)** — Initial release. Captures the six-step repair workflow for dead "pull from X" builders on Pipe, the seven-test TDD matrix, the deep-copy-before-merge rationale, the merge-order contract, and the `--rerun-tasks` verification ritual. Repair transcript archived in `references/repair-session-2026-07-22.md`.

## Cross-references

- `tpipe-pipe-internals` — the broader Pipe internals skill that already covers the defect discovery side. This repair skill extends it on the fix side.
- `software-development:interactive-plan` — the workflow used to ship this fix; Phase 1 capture, Phase 2 interview (scope clarification), Phase 3 plan + approval, Phase 3.5 tracking-mode gate, Phase 4 execute via todos.
- `software-development:test-driven-development` — the RED-GREEN-REFACTOR cycle applied here.
- `software-development:verifying-code-changes` — post-edit verification ritual.