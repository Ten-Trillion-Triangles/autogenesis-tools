# ConverseRole.harness — the role tier for harness-injected messages

**Captured:** 2026-07-24 (5 sites, all flipped in one commit, fix landed on `main` as `72d88962`).

## The bug

The five harness-injected hint sites were tagging their messages as `ConverseRole.user`. That's role fraud: `ConverseRole.user` is the LLM provider's contract for human-user input. Harness corrections are not user intent. The LLM may weight the message as authoritative user instruction, downstream tools that distinguish user input from system instructions will misclassify the hint, and the prompt is now lying about the source of the message.

The bug was class-level: any site that injects a message into `turnHistory` had picked the wrong role. The 5 sites all shared the same anti-pattern but were not visible as a class until the question was asked.

## Why `system` is also wrong

`ConverseRole.system` looks closer to the right answer (it's the harness's "infrastructure" role, not user input) but it has a different problem. The context-trimming rule at `Pipeline/PumpStationLoop.kt:1015` keeps only the most-recent `system` message:

```kotlin
// Rule 3: keep only the most-recent system message
val lastSystemIndex = turns.indexOfLast { it.role == ConverseRole.system }
turns = turns.filterIndexed { i, turn ->
    turn.role != ConverseRole.system || i == lastSystemIndex
}
```

That behavior is correct for the LLM's system prompt (a single coherent instruction set), but wrong for harness corrections (which are appended as the harness runs, not authored as a single block). Putting hints in `system` would silently prune all but the most-recent hint — exactly the wrong behavior for the one-shot semantics the hints are designed around.

## The fix

Added a new `ConverseRole.harness` enum value. The KDoc on the enum documents the role's contract:

```kotlin
/**
 * Messages emitted by the PumpStation harness itself: path-safety
 * rejection hints, empty-pathName hints, empty-rationale nudges,
 * pathSchema-fallback hints, DITL steering entries. Distinct from
 * [system] (which is pruned to the most-recent message by the
 * context-trimming rule at PumpStationLoop.kt:1015 — a behavior
 * intentional for the LLM's system prompt but wrong for harness
 * corrections, which must survive context pressure) and from [user]
 * (which is the LLM provider's contract for human-user input —
 * harness corrections are not user intent).
 */
harness
```

Flipped 5 call sites:

| File:line | Hint kind | Hint marker prefix |
|---|---|---|
| `Pipeline/PumpStation.kt:3067` | Path-safety rejection | `[Path Safety] Path '<X>' was rejected by the path-safety gate...` |
| `Pipeline/PumpStationLoop.kt:188` | DITL steering entries | varies — DITL author defines |
| `Pipeline/PumpStationLoop.kt:419` | Empty-pathName dispatch | `[Harness Notice] dispatch pathName was empty` |
| `Pipeline/PumpStationLoop.kt:914` | pathSchema-fallback | `[Harness Notice] pathSchema did not deserialize...` |
| `Pipeline/PumpStationLoop.kt:3274` | Empty-rationale nudge | `[Harness Notice] pathSelectionRationale was empty` |

## The 3-tier system-prompt hierarchy

After the fix, the conversation message-source hierarchy the LLM sees is:

1. **`ConverseRole.system`** — the LLM's system prompt (personality, systemTask, userGuidelines, entryUserPrompt). One block, pruned to most-recent.
2. **`ConverseRole.harness`** — runtime corrections from the PumpStation harness. Many messages, all preserved. Distinct from `system` so the pruning rule doesn't touch them.
3. **`ConverseRole.user`** — actual user input (only the entry prompt, not the harness's user-message history which now uses `harness`).

`ConverseRole.assistant` is the LLM's own output (path results, judge verdicts, etc.). `ConverseRole.tool_response` / `pcp_response` / `mcp_response` are tool-call results. `ConverseRole.agent` / `supervisor` / `developer` are reserved for future use.

## Test coverage

`ConverseRoleHarnessHintTest` (`src/test/kotlin/Pipeline/`) — 4 tests:

1. **`ConverseRole enum declares the harness tier`** — pins the enum surface so a future refactor can't silently drop the role.
2. **`path-safety hint uses ConverseRole.harness`** — pins the path-safety hint's role assignment.
3. **`steering injection uses ConverseRole.harness`** — pins the DITL steering injection's role assignment.
4. **`no production code emits ConverseRole user for harness hints`** — static-analysis guard that scans `Pipeline/PumpStation.kt` and `Pipeline/PumpStationLoop.kt` for any future `ConverseRole.user` site. If a future patch adds a 6th hint site and uses the wrong role, this test fails.

## Pattern for future hint sites

When adding a new harness-emitted message:

1. The `ConverseData` constructor MUST use `role = ConverseRole.harness`.
2. The new site MUST have a test that asserts the role.
3. If the new site is at a new file, add it to the static-analysis guard in `ConverseRoleHarnessHintTest::no production code emits ConverseRole user for harness hints`.

The role is not a "free pick" — it's part of the contract that the LLM prompt's message-source hierarchy depends on.

## What this fix does NOT do

- Does NOT change `ConverseRole.system`'s pruning behavior. The pruning rule at `PumpStationLoop.kt:1015` is correct for system prompts and would be wrong to change. `harness` is a separate tier that bypasses the pruning.
- Does NOT add a similar tier for the LLM's `assistant` messages. `assistant` is the LLM's own output and follows a different lifecycle (path results, judge verdicts). The existing `ConverseRole.assistant` is already correctly used.
- Does NOT add a tier for tool responses. `tool_response` / `pcp_response` / `mcp_response` are already separate tiers and are used correctly.
- Does NOT change the path-safety hint's dedup behavior. The hint's per-pathName dedup is a separate concern (Defect 27 in `harness-defect-catalog.md`). This fix only changes the role assignment.

## Related

- `pump-station/SKILL.md` "ConverseRole tier for harness-injected messages" — top-level skill entry summarizing this fix.
- `pump-station/SKILL.md` "harness-defect-catalog" Defect 27 — the path-safety hint's dedup behavior, orthogonal to the role assignment.
- `pump-station/SKILL.md` "Path-name case-insensitive registry" — sibling class-level pattern about map-key boundary contracts in PumpStation.
