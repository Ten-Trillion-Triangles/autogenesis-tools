# Example — Adding `reasoningCaptureFunction` and `finalCaptureFunction` to `Pipe.kt`

Captured 2026-07-22. Worked example of the full DITL-hook pattern: field, setter, invocation wiring across multiple sites, doc updates, and verification.

## The two hooks added

```kotlin
@kotlinx.serialization.Transient
var reasoningCaptureFunction: (suspend (content: MultimodalContent, reasoning: String) -> Unit)? = null

@kotlinx.serialization.Transient
var finalCaptureFunction: (suspend (content: MultimodalContent) -> Unit)? = null
```

`reasoningCaptureFunction` fires inside `injectTPipeReasoning` with the raw reasoning string before any injection variant mutates content. `finalCaptureFunction` fires on every `return@coroutineScope` site in `executeMultimodal`.

## Signature change required

`injectTPipeReasoning` was non-suspending. To call the suspending `reasoningCaptureFunction` from inside it, the signature changed:

```kotlin
// Before
private fun injectTPipeReasoning(content: MultimodalContent)

// After
private suspend fun injectTPipeReasoning(content: MultimodalContent)
```

The single caller at `Pipe.kt:6354` was already inside `executeMultimodal`'s `coroutineScope { ... }`, so it needed no edit. Verify each caller is already in a suspending context before assuming this works.

## Invocation wiring

`reasoningCaptureFunction` — single call site at the top of `injectTPipeReasoning`, immediately after `val reasoningOutput = content.modelReasoning`:

```kotlin
reasoningCaptureFunction?.invoke(content, reasoningOutput)
```

`finalCaptureFunction` — six call sites in `executeMultimodal`, one per `return@coroutineScope` exit point. Three shapes:

Shape A — variable already exists:
```kotlin
val cleanedFinal = finalResult.apply { text = cleanResponseText(finalResult.text) }
finalCaptureFunction?.invoke(cleanedFinal)
return@coroutineScope embedContentIntoInternalConverse(cleanedFinal).takeIf { wrapContentWithConverseHistory } ?: cleanedFinal
```

Shape B — return-wrap (needed when the return expression IS the call you want to capture):
```kotlin
val execResult = executionFunction!!.invoke(content, station, turnHistory, turnSummary)
finalCaptureFunction?.invoke(execResult)
return execResult
```

Shape C — failure path on a fresh local:
```kotlin
val failedContent = MultimodalContent()
failedContent.pipeError = lastError
finalCaptureFunction?.invoke(failedContent)
return@coroutineScope failedContent
```

## Verification script shape

Ad-hoc Python script at `/tmp/hermes-verify-ditl-invocation-<date>.py`:

```python
import re, sys

src = open("src/main/kotlin/Pipe/Pipe.kt").read()

# 1. Field declarations (regex match the @Transient + var + suspend shape)
field_reasoning = re.search(
    r"@kotlinx\.serialization\.Transient\s*var\s+reasoningCaptureFunction\s*:",
    src,
)
assert field_reasoning

# 2. Setter assigns field, returns this
setter = re.search(
    r"fun\s+setFinalCaptureFunction[^}]*finalCaptureFunction\s*=\s*func\s*;?\s*return\s+this",
    src,
)
assert setter

# 3. Count invocation sites
final_invs = list(re.finditer(r"finalCaptureFunction\?\.invoke\s*\(\s*(\w+)\s*\)", src))
assert len(final_invs) == 6  # expected return-site count

# 4. Each invocation paired with the expected variable in the return statement
for m in final_invs:
    var = m.group(1)
    tail = src[m.end():m.end()+800]
    assert re.search(r"return@coroutineScope\b[^;]*\b" + re.escape(var) + r"\b", tail)

# 5. Brace balance after stripping strings + comments
clean = re.sub(r'/\*.*?\*/', '', src, flags=re.DOTALL)
clean = re.sub(r'"""[^"]*"""', '""""""', clean)
clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', clean)
assert clean.count("{") == clean.count("}")

# 6. Sibling hooks preserved
for hook in ["preInitFunction?.invoke", "preInvokeFunction?.invoke",
             "postGenerateFunction?.invoke", "validatorFunction?.invoke",
             "onFailure?.invoke"]:
    assert hook in src
```

## Doc updates in the same turn

Three files touched:

- `docs/core-concepts/developer-in-the-loop.md` — change "seven key intervention points" → "nine"; extend numbered list 7 → 9; extend execution-order arrow diagram to include `Reasoning Capture` (between AI Call and Post-Generate) and `Final Capture` (between On-Failure and Output); add two new `## Hook Name Function` sections matching the existing prose+KDoc+code-example shape; add TOC entries.
- `docs/api/pipe.md` — add two `#### ` setter entries in the "Function Hooks" section between `setPostGenerateFunction` and `setOnFailure`. Each cites `Pipe.kt:<line-number>` for traceability.
- `docs/core-concepts/reasoning-pipes.md` — extend the "How It Works" step list (4 → 5 steps) in the reasoning-injection lifecycle. Renumber subsequent steps. New step mentions `reasoningCaptureFunction` firing inside `injectTPipeReasoning`.

## Gotchas hit during this session

- **Markdown-table bleed**: transcribing `**What it does**` from inside a markdown table row produced `|**What it does**` (extra leading pipe) in two patched sections. Caught by the verification script's regex `\b\*\*What it does\*\*\b` failing. Fix: replace `|\*\*What it does\*\*` with `**What it does**` across the file.
- **Stray closing code fence**: when patching the execution-order diagram block, the old_string included a blank line that swallowed an extra ` ``` ` line, leaving 5 closing fences instead of 4. Fix: verify code-fence balance (count of `^```$` lines must be even).
- **Indent-collapse on second final-capture patch**: the second `finalCaptureFunction` insertion (site 2) over-supplied an over-indented old_string, so the fuzzy matcher collapsed the surrounding 5-line block indent by 2 levels. Caught on the next read_file. Fix: revert via corrective patch using EXACT-match whitespace for blocks deep inside nested `when` cascades.

## Verification result

17/17 checks PASS on first full run (after the three gotchas were fixed individually). The single full run after all three gotchas were resolved was clean.

## Lesson for the next session

- The DITL-hook shape is now stable: `@Transient var` + nullable `suspend (MultimodalContent...) -> Unit` + builder setter returning `this` + invocation at each return site. Future hooks on `Pipe` or `PathObject` follow this exact pattern.
- The doc-update surface is also stable: any new Pipe DITL hook requires updates to `developer-in-the-loop.md` (count + bullets + diagram + new section + TOC), `pipe.md` (Function Hooks setter entry), and (for reasoning hooks only) `reasoning-pipes.md` (How It Works step list).
- The verification script shape is reusable — copy and adapt per-feature.