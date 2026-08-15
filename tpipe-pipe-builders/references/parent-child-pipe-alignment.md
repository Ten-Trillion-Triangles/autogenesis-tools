# Parent / child pipe alignment audit

**Use when**: migrating any host pipe's `setModel(...)` line (model A
→ model B), auditing an existing agent whose host pipe and reasoning
pipe should share the same model, or chasing a silent regression
where host pipe behavior matches one model but reasoning-pipe behavior
matches another.

**Verified**: 2026-07-30, Autogenesis PalmyraX5 → qwenCoder30B cutover —
caught 7 reasoning-pipe sites that had silently retained the prior
default after the host pipe's `setModel(...)` was migrated. Both
`PalmyraX5ToG31bMigrationTest` and the qwen-style host-pipe tests
were passing because they asserted pipe *types* and the host's
`pipeName`, never the reasoning pipe's model.

## The bug class

When a host pipe's `setModel(BedrockConfig.X)` line is migrated from
model A to model B, the inner
`setReasoningPipe(BedrockConfig.authorBuilder(<char>, depth = ..., ...))`
slot may not migrate in lockstep. Two patterns leave the reasoning
pipe silently on the prior default:

```kotlin
// Pattern 1: bare authorBuilder call (no explicit model)
setReasoningPipe(BedrockConfig.authorBuilder(charProfile, depth = High, duration = Short))

// Pattern 2: authorBuilder call with inner setModel that didn't migrate
setReasoningPipe(BedrockConfig.authorBuilder(charProfile, depth = High, duration = Short).apply {
    setModel(BedrockConfig.<prior-default>)   // stale
    setTokenBudget(BedrockConfig.<prior-budget>)  // stale
})
```

The `authorBuilder` default `model: String = ...` parameter is the
fallback. Pre-cutover that default was `PalmyraX5`; the cutover moved
it to `qwenCoder30B`. Both transitions are silent — no compile error,
no runtime exception, just a reasoning pipe that's on a different
model than the host pipe's `setModel(...)` says it should be.

## Why the existing test suite didn't catch it

The `PalmyraX5ToG31bMigrationTest` (and similar test classes that
pin pipe types post-cutover) assert:

- `assertIs<GenericOpenAIPipe>(host, ...)` — host pipe *type*
- `assertIs<GenericOpenAIPipe>(branch, ...)` — branch pipe *type*
- `assertTrue(reasoning.pipeName.contains("g31b", ignoreCase = true), ...)` — reasoning pipe name has the factory marker

None of those assertions check the reasoning pipe's `model` field.
`Pipe.model` is **protected** (not directly readable from outside the
package). `GenericOpenAIPipe.bedrockMantleAuth` is **private**. The
public observable surface doesn't expose the reasoning pipe's model
unless you go through a live test.

This is the gap. The migration test was checking the surface that was
mechanically safe to migrate (host pipe constructor + factory name)
and silently skipping the surface that was the actual risk (inner
reasoning pipe's `setModel` call).

## Audit recipe — find misaligned sites

For any host pipe whose `setModel(...)` line changed, find its
matching `setReasoningPipe` and inspect the inner call:

```bash
# Show the diff of every setReasoningPipe site in agent/builders
git diff --unified=3 -- 'server/src/main/kotlin/agent/builders/**' | \
    grep -B2 -A6 'setReasoningPipe(BedrockConfig\.authorBuilder'
```

A site is **misaligned** when, looking at the inner
`authorBuilder(...)` call:

1. The call signature has no `model = ...` kwarg, AND
2. The call is not immediately followed by `.apply { setModel(...) }`

Either of those is required to override the `authorBuilder` default.
Bare calls silently inherit the default.

## Fix shape

Wrap each misaligned `authorBuilder(...)` call in
`.apply { setModel(<parent-model>); setTokenBudget(<parent-budget>) }`
so the source reads unambiguously even if `authorBuilder`'s default
ever changes again:

```kotlin
// Before (silently inherits authorBuilder default)
setReasoningPipe(BedrockConfig.authorBuilder(charProfile, depth = High, duration = Short))

// After (parent/child explicitly aligned)
setReasoningPipe(BedrockConfig.authorBuilder(charProfile, depth = High, duration = Short).apply {
    setModel(BedrockConfig.qwenCoder30B)
    setTokenBudget(BedrockConfig.generativeBudgetSettings)
})
```

The outer `setModel(<parent-model>)` on the host pipe and the inner
`setModel(<parent-model>)` on the reasoning pipe now match in source.
The next time anyone changes the host pipe's model, the audit grep
above will flag the reasoning pipe site too — no silent drift.

## The 7 sites from the 2026-07-30 PalmyraX5 cutover

Concrete examples from the Autogenesis codebase that were caught by
this audit (each had a `setModel(BedrockConfig.qwenCoder30B)` on the
host but a bare `authorBuilder(...)` on the reasoning pipe):

| File:Line | Parent pipe (model) | Reasoning pipe (pre-fix) |
|---|---|---|
| `writerAgent.kt:200` | `guidePipe` (qwenCoder30B) | `authorBuilder(effectiveGuideAuthorPersonality, depth = High, duration = Short)` |
| `writerAgent.kt:445` | `selectionPipe` (qwenCoder30B) | `authorBuilder(effectiveGuideAuthorPersonality, depth = High, duration = Long)` |
| `elderGodAgent.kt:130` | `targetPipe` (qwenCoder30B) | `authorBuilder(npcPrompt, depth = High, duration = Short, showThinking = true, ...)` |
| `elderGodAgent.kt:181` | `actionPipe` (qwenCoder30B) | `authorBuilder(npcPrompt, depth = Low, duration = Short, showThinking = true, ...)` |
| `npcHostileAgent.kt:88` | `optionsPipe` (qwenCoder30B) | `authorBuilder(npcPrompt, depth = High, duration = Long, showThinking = true, ...)` |
| `npcHostileAgent.kt:130` | `actionsPipe` (qwenCoder30B) | `authorBuilder(npcPrompt, depth = High, duration = Long, showThinking = true, ...)` |
| `npcActorAgent.kt:73` | `npcActorPipe` (qwenCoder30B) | `authorBuilder(npcPrompt, depth = Low, duration = Short, showThinking = true, ...)` |

Two additional sites (already correct at the start) had been
explicit-aligned earlier and serve as the proof pattern:

- `chatAgent.kt:47-50` — `.apply { setModel(BedrockConfig.qwenCoder30B); setTokenBudget(BedrockConfig.generativeBudgetSettings) }` wrapped around the authorBuilder call.
- `ValidatorPipeAgent.kt:136` — passes `model = BedrockConfig.qwenCoder30B` as an `authorBuilder` kwarg.
- `playerAgent.kt:61` — passes `model = BedrockConfig.qwenCoder30B` as an `authorBuilder` kwarg; parent pipe here is Mantle E2B, reasoning is qwen — intentional mixed-mode (different reasoning budget).

## Validation script shape

The post-edit verification script that proved the audit covered every
site was the hermetic `/tmp/hermes-verify-palmyrax5-cutover.sh`
recipe (also captured in operator memory as the
`Hermetic ad-hoc verifier script pattern`). For the audit specifically,
the relevant check shape is:

```bash
# For each known misaligned site (post-edit line numbers), verify the
# next ~12 lines contain both setModel(parent-model) AND
# setTokenBudget(parent-budget).
check_alignment() {
    local file="$1" line="$2" name="$3"
    if sed -n "${line},$((line+12))p" "$file" | grep -q 'setModel(BedrockConfig.<parent>)' \
       && sed -n "${line},$((line+12))p" "$file" | grep -q 'setTokenBudget(BedrockConfig.<parent-budget>)'; then
        echo "PASS: $name aligned at $file:$line"
    else
        echo "FAIL: $name NOT aligned at $file:$line"
        exit 1
    fi
}

check_alignment server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt 200 \
    "writerAgent guidePipe reasoning"
check_alignment server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt 445 \
    "writerAgent selectionPipe reasoning"
# ... one check per site in the audit list
```

The line numbers are anchored to the post-edit file state; if a
future patch shifts them, the script must be updated. The audit list
above is the canonical set for the 2026-07-30 PalmyraX5 cutover; new
cutovers produce new lists.

## When to apply this audit

Trigger the audit on any of:

- A host pipe's `setModel(...)` line is changed (model swap)
- An `authorBuilder` default parameter is changed
- A new agent is added whose reasoning pipe is wired via `setReasoningPipe(BedrockConfig.authorBuilder(...))`
- A test class asserts host pipe type but not reasoning pipe model (gap like the one the cutover uncovered)

The audit is fast (one grep + one sed per file) and prevents a class
of regression that's invisible to the existing test surface.