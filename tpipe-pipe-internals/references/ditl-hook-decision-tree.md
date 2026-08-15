# DITL Hook Decision Tree

Use this when a user describes what they want to observe or intercept in the
Pipe lifecycle and you need to pick the right hook, or propose a new one.

## Step 1 — Identify the lifecycle moment

Map the user's description to one of these moments:

| User phrasing (typical) | Lifecycle moment |
|---|---|
| "before the pipe runs" / "setup" / "preconditions" | pre-init |
| "before the LLM is called" / "should I skip this pipe?" | pre-invoke |
| "the raw LLM response" / "right after the model generated" | post-generate |
| "is this content good enough?" / "should we retry?" | validation |
| "the final output before it exits" / "outer scaffolding" / "harness interception" | post-transformation |
| "what just went wrong?" / "handle the failure" | failure |
| "I want to see the reasoning" / "show me the thinking" | reasoning-capture |

## Step 2 — Match to existing hook

| Lifecycle moment | Existing hook | Signature shape | Field line | Setter line |
|---|---|---|---|---|
| pre-init | `preInitFunction` | `Unit` observer | ~1451 | ~4327 |
| pre-invoke | `preInvokeFunction` | `Boolean` gate | ~1493 | ~4372 |
| reasoning-capture | `reasoningCaptureFunction` | `Unit` observer + reasoning string | ~1501 | ~4412 |
| post-generate | `postGenerateFunction` | `Unit` observer | ~1503 | ~4382 |
| validation | `validatorFunction` | `Boolean` gate | ~1510 | ~4272 |
| post-transformation | `transformationFunction` | `MultimodalContent` mutator | ~1524 | ~4314 |
| post-transformation (observe-only) | `finalCaptureFunction` | `Unit` observer on every return | ~1537 | ~4425 |
| failure | `onFailure` | `MultimodalContent` mutator | ~1531 | ~4408 |

## Step 3 — Decide observer vs mutator

- Observer (`Unit`-returning): for telemetry, UI sinks, logging, audit.
  The hook does not alter the content. The pipeline continues unchanged.
- Mutator (`MultimodalContent`-returning): for content transformation,
  filtering, redaction, format conversion. The hook can replace the content
  that the pipeline continues with.
- Gate (`Boolean`-returning): for skip/retry decisions.

When in doubt, prefer observer — it cannot break the pipeline. Switch to
mutator only if the user needs the change to actually propagate downstream.

## Step 4 — Decide whether to propose a NEW hook

Before proposing a new hook, confirm:

- The user's lifecycle moment is NOT served by any existing hook.
- The user's signature shape need is NOT served by any existing hook.
- The user has confirmed they want a separate hook (rather than composing
  multiple observers inside an existing hook body — the standard pattern).

If any of those is satisfied by the existing 8 hooks, point the user at the
existing hook instead of designing a new one. Do NOT add a new hook just
because the user said "add a hook for X" — first check whether X is already
covered by what exists.

## Worked examples

### "I want to capture the final output just prior to exiting to the parent"

Lifecycle moment: post-transformation. Two candidates:
- `transformationFunction` (existing) — fires once per successful path through
  transformation. Returns `MultimodalContent` so it is a mutator slot. Use as
  observer by returning input unchanged.
- `finalCaptureFunction` (added 2026-07-22) — fires on every return path
  (success, branch, failure-recovery, terminated, caught exception). Pure
  observer.

Pick `transformationFunction` if the user wants only successful outputs.
Pick `finalCaptureFunction` if the user wants every terminal content object
including failures.

### "I want to see the reasoning content the model produced"

Lifecycle moment: reasoning-capture. Two candidates:
- `reasoningCaptureFunction` (added 2026-07-22) — gives you the raw
  `content.modelReasoning` BEFORE it is unraveled into prose. Best for
  structured reasoning UI (thinking panels, collapsible accordions).
- `transformationFunction` / `finalCaptureFunction` — read `content.text`
  to see the post-injection prose. Best for "show the user the full
  assembled prompt" sinks.

Pick `reasoningCaptureFunction` if you need the structured reasoning field.
Pick a final hook if you only care about the prose form.

### "I want to know when the pipe fails"

Lifecycle moment: failure. Two candidates:
- `onFailure` — fires on failure paths with both the original input and the
  processed (failed) content. Use for retry logic, content repair, or
  failure-driven fallbacks.
- `finalCaptureFunction` — fires on terminated (`shouldTerminate`) and caught
  exception returns too, but with no original/ processed distinction.

Pick `onFailure` if you need to mutate the failure output or compare
original vs processed. Pick `finalCaptureFunction` if you only need to
observe the terminal content (and want to write the same hook for both
success and failure paths).

## Anti-patterns

- Adding a new hook when an existing one already serves the lifecycle
  moment. (See `SKILL.md` pitfall "Given the user's goal, look for the
  closest existing hook first.")
- Returning `Unit` from a `MultimodalContent`-shaped hook by ignoring the
  return value (the Kotlin compiler will not catch this; use the
  hook-as-observer pattern explicitly with a docstring noting intent).
- Using `transformationFunction` as a pure observer on the assumption that
  it fires once per `execute()` — it fires on multiple paths, so dedupe
  any side-effecting body.