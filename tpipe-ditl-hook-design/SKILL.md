---
name: tpipe-ditl-hook-design
description: "Adding Developer-in-the-Loop (DITL) hooks to TPipe Pipe and PathObject classes. Covers the field/setter/invocation contract, the suspend-modification rule, the return-wrap pattern, site-selection discipline, doc updates, and verification."
version: 1.0.0
metadata:
  hermes:
    tags: [tpipe, ditl, hooks, extension-points, kotlin, builder-pattern, suspending-callbacks, pipe, pathobject]
    related_skills: [tpipe-pipeline-patterns, apex-coder, interactive-plan]
---

# TPipe DITL Hook Design

## Overview

Developer-in-the-Loop (DITL) hooks are the extension-point surface on TPipe's `Pipe` and `PathObject` classes — nullable `suspend` callbacks that fire at specific lifecycle stages, allowing outer-scaffolding UI/UX sinks (GUIs, TUIs, agent harnesses, telemetry) to observe and respond to pipe/path behavior without altering the dispatch flow.

When you need to add a new extension point to `Pipe` (LLM-call lifecycle) or `PathObject` (path-dispatch lifecycle), this skill governs the convention. It does NOT govern the rest of the TPipe DSL design — that is `tpipe-pipeline-patterns`.

## Trigger conditions

Add a new DITL hook when:
- A consumer needs to observe a specific lifecycle stage on `Pipe` or `PathObject` (e.g. raw reasoning output, final pipe content, path dispatch result)
- The hook fits an existing DITL category: pre-init, pre-validation, pre-invoke, post-generate, validator, transformation, on-failure, or the new capture categories (reasoning-capture, final-capture, output-capture)
- The hook receives one of: `MultimodalContent` (most common), `MultimodalContent + String` (reasoning-capture shape), or `MultimodalContent + Throwable` (on-failure shape)

## Conventions

### Field shape

```kotlin
@kotlinx.serialization.Transient
var hookName: (suspend (content: MultimodalContent) -> Unit)? = null
```

The four invariants:
- `@kotlinx.serialization.Transient` — the hook is NOT serialized into any config snapshot
- Nullable (`?`) — the hook is optional; consumers opt in via the setter
- `suspend` — the hook may need to do async I/O (UI sink, telemetry write)
- Returns `Unit` — the hook observes, never mutates the pipeline result

### Setter shape

```kotlin
fun setHookName(func: suspend (content: MultimodalContent) -> Unit): Pipe
{
    hookName = func
    return this
}
```

Returns `this` for chaining. The setter name is `set{FieldName in PascalCase}`. Match the surrounding class's existing setter convention — `Pipe` uses `setPostGenerateFunction`, `setTransformationFunction`, etc. (with `Function` suffix); `PathObject` uses `setInternalAgent`, `setExecutionFunction`, `setOutputCaptureFunction` (no `Function` suffix on capture-style hooks). Match the local pattern.

### Invocation shape

```kotlin
hookName?.invoke(content)
```

Inline at the lifecycle stage. `await`-ed implicitly by `suspend` semantics — no `async { ... }` wrapper unless the consumer's downstream pipeline needs fire-and-forget. Inline `await` ensures ordered delivery.

### KDoc on the field

Every hook field gets a KDoc block that:
- States what the hook observes
- States when it fires relative to other lifecycle stages
- Cross-references the setter (`@see setHookName` or `@see [hookName]` depending on class convention)
- Notes any suspend semantics that consumers should know about

### KDoc on the setter

Match the setter KDoc convention used by the surrounding class. `Pipe` setters use `@see [fieldName]` cross-references; `PathObject` setters use plain prose descriptions.

## The suspend-modification rule

**If you need to call a suspending hook from a non-suspending function, make the calling function `suspend`.**

Concretely: `Pipe.executeMultimodal` is already suspending (it lives inside `coroutineScope { ... }`). `Pipe.injectTPipeReasoning` was non-suspending until `reasoningCaptureFunction` needed a suspending hook — the fix was changing `private fun` to `private suspend fun`. The single caller at line 6354 needed no change because it was already in a suspending context.

Verification: after the signature change, run a grep for callers of the modified function and confirm each caller is already in a suspending context. If any are not, you need to bridge with `runBlocking` (avoid if possible) or make the caller suspending too.

## The return-wrap pattern

When the hook fires before a `return <expression>` and the hook needs to see the result of that expression, wrap the return:

Before:
```kotlin
return executionFunction!!.invoke(content, station, turnHistory, turnSummary)
```

After:
```kotlin
val execResult = executionFunction!!.invoke(content, station, turnHistory, turnSummary)
hookName?.invoke(execResult)
return execResult
```

This is necessary because the original `return <expr>` form evaluates `<expr>` as the return value; you cannot capture that intermediate result without the local. The priority dispatch logic is unchanged.

## Site-selection discipline

Decide which return paths get the hook. Three modes:

1. **Success-only** — fire only on successful returns. Conservative; consumers see clean output.
2. **All success-shaped paths** — fire on every path that returns a `MultimodalContent`. Includes branch success, failure-recovery success, transformation success.
3. **All return paths including failure** — fire on every `return@coroutineScope` and `return@coroutineScope failedContent`. Captures the user's full pipe execution state.

Default for new capture-category hooks: **mode 3** (all paths). Outer-scaffolding consumers want to observe everything, including failures. The hook is `Unit`-returning so it cannot affect control flow.

For mode-3 wiring, count the `return@coroutineScope` sites carefully. For `Pipe.executeMultimodal`, there are six: validator-passed success, no-validator success, branch success, failure-recovery success, terminated (pipe error), exception-caught.

For `PathObject`, there are five: PCP, executionFunction, internalAgent, agentBuilderFunction, executeLocal. Throw paths (no-mechanism `IllegalStateException`, kill-switch-tripped `throw trip`) do NOT fire the hook because there is no `MultimodalContent` to hand to the consumer.

## Doc updates

When adding a new hook to `Pipe`, update these docs in the same turn (or as a follow-up plan):

- `docs/core-concepts/developer-in-the-loop.md` — extend the numbered list and execution-order diagram. Update "X key intervention points" → the new count. Add a `## Hook Name Function` section matching the existing format. Add a TOC entry.
- `docs/api/pipe.md` — add a `#### ` entry in the "Function Hooks" section. Cite `Pipe.kt:<line-number>` for traceability.
- `docs/core-concepts/reasoning-pipes.md` (reasoning-capture only) — extend the "How It Works" step list in the injection lifecycle section. Renumber subsequent steps.

When adding a new hook to `PathObject`, no doc updates are usually needed because no path-level DITL hook is currently enumerated in the docs. (If you want to track this for completeness, add a section to `docs/api/pumpstation.md` and `docs/core-concepts/pumpstation-magic-contracts.md` in a follow-up plan.)

## Verification pattern

Ad-hoc Python script under `/tmp/hermes-verify-<feature>-<date>.py` with checks for:

1. Field declared with correct signature (use a regex matching the `@Transient var hookName: (suspend ... -> Unit)?` shape)
2. Setter body assigns field and returns `this` (the chained-return signature)
3. Exactly N invocation sites (count = number of returns you intended to wrap)
4. Each invocation paired with the expected local variable in the return statement (regex `return@coroutineScope ... <var>` within ~3 lines after the invocation)
5. Brace balance clean after stripping block comments and string literals (strings can contain unmatched `{` chars that throw off naive counts)
6. Sibling hooks preserved (no regression on existing DITL hook call sites)

Cleanup: `rm -f /tmp/hermes-verify-<feature>-<date>.py` after the run. Report results as ad-hoc verification, not suite-green.

## Pitfalls

- **Class-API paraphrase (Pitfall 12 extension)**: Before writing a plan that touches `PathObject` or `Pipe` internals, run a 3-call probe — (1) locate the class file via `grep -rn "class <Name>" <root>`, (2) enumerate public mutable fields via `grep -nE "    var [a-z]... = " <file>`, (3) enumerate public methods (including extension-function methods) via `grep -nE "fun bindFunction|fun set[A-Z]|fun get[A-Z]|val is[A-Z]|val has[A-Z]" <file>` AND any `*Extensions.kt` files in the same package. Each call is 1-2 seconds. Together they pin the surface the plan can rely on. Real session (2026-07-22): verified `dispatchHint`, `pathMetadata`, and the `bindFunction` extension function on `PathObject` before designing the standalone DSL.
- **Suspend-modification blind spot**: When you change a function from `fun` to `suspend fun`, the call site also needs to be in a suspending context. Run `grep -rn "<funcName>\("` and verify each caller's enclosing context. If a non-suspending caller exists, you need to bridge with `runBlocking` (avoid if possible) or make the caller suspending too.
- **Return-wrap not applied uniformly**: A common mistake is to apply the return-wrap pattern to sites 1-4 but forget site 5 (or vice versa). Count `return@coroutineScope` sites BEFORE you start, count invocation sites AFTER. The two numbers must match.
- **Doc-update lag**: Adding a hook to code without updating the docs leaves the docs stale. The "X key intervention points" sentence in `developer-in-the-loop.md` is a smoke-test — if it says "seven" and you added the eighth hook, the doc is wrong.
- **Markdown-table bleed**: When transcribing a `**bold**` phrase from inside a markdown table row to a section heading, the surrounding `|` chars can sneak into the new copy, producing `|**What it does**` instead of `**What it does**`. After editing, grep for `|\*\*` patterns to catch the bleed.
- **Stray closing code fence**: When patching around an execution-order diagram block, a duplicated closing ``` can sneak in if the old_string includes the surrounding blank lines. Verify code-fence balance after the patch (count of `^```$` lines must be even).

## References

- `references/example-pipe-final-capture.md` — worked example from 2026-07-22 adding `reasoningCaptureFunction` and `finalCaptureFunction` to `Pipe.kt`, plus the matching doc updates to `developer-in-the-loop.md`, `pipe.md`, and `reasoning-pipes.md`.

## Related skills

- `tpipe-pipeline-patterns` — TPipe pipeline composition, not DITL hooks
- `apex-coder` — general TPipe coding discipline (TDD, builder pattern, third-party class API paraphrasing)
- `interactive-plan` — workflow for multi-step plan → execute → deliver with Phase 3.5 tracking gate