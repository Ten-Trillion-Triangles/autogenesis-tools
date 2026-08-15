# Diagnostic Gate: 4-Step Method to Rule Out Fabricated Hypotheses

The 4-step diagnostic gate is a concrete technique that emerged from the
2026-07-23 path-safety rejection triage session. It was applied to rule
out a fabricated hypothesis (the LLM never received the user's original
input) and proved the hypothesis wrong using live trace evidence.

## The 4 steps

1. **Count invocations.** In the failing trace, count
   `PUMP_STATION_PATH_STARTED` events. If N≥2, the LLM has been called
   multiple times — single-call hypotheses (e.g. "the LLM never
   received the input") are unlikely.

2. **Read input chars per invocation.** Look at
   `PUMP_STATION_PATH_COMPLETED` `text` field. If the path's output
   is ≥1 keyword from the user's input, the LLM received the input. If
   the output is generic boilerplate (≤50 chars) AND the user input
   was longer (≥50 chars), the input chain is broken.

3. **Compare output topic to user input topic.** Extract 3-5 key words
   from the user's original input (from `PUMP_STATION_STARTED` meta
   `originalInputPreview`). Search for those words in the path's
   output. If N/M words match, the LLM knew the task.

4. **Only then issue a verdict.** If steps 1-3 pass, the LLM received
   the input and the bug is downstream (LLM behavior, harness
   governance, path selection, etc.). If any step fails, the bug is
   upstream (input routing, prompt construction, etc.).

## Worked example: live-04

User asked: "is the bug that the LLM never received the user's original
input?"

**Step 1:** `PUMP_STATION_PATH_STARTED` count = 47. N≥2; single-call
hypothesis unlikely.

**Step 2:** First `PUMP_STATION_PATH_COMPLETED` text = "Findings on Run
the post-goal hook harness.: 3 substantive points." (71 chars). User
input was 31 chars ("Run the post-goal hook harness."). The output is
71 chars and contains the user's key phrase "Run the post-goal hook
harness."

**Step 3:** 3/3 key words from user input ("Run", "post-goal", "hook",
"harness") match the output. Verdict: **LLM RECEIVED INPUT**.

**Step 4:** Hypothesis REFUTED. The bug is NOT "input not reaching LLM."
The bug is downstream — likely F1 (the `alreadyNudged` one-shot gate
at `PumpStation.kt:3025-3041`) or the missing give-up path (which the
user then directed the agent to add to the live test).

## When to use

When a hypothesis about harness behavior can be ruled out by looking
at the live trace, run the gate. The gate produces a `VERDICT` column
in a per-test summary table that explicitly states whether the LLM
received the input, the input chars per invocation, and the topic
match. The verdict is mandatory before publishing a "Bug X is the
cause" report.

## Verification table format

| TEST | PATHS | INPUT_LEN | TOPIC_MATCH | VERDICT |
|------|-------|-----------|-------------|---------|
| 01-always-on-judge | 3 | 4988 | 3/5 words | LLM RECEIVED INPUT |
| 04-kill-switch-trip | 0 | 0 | N/A | no paths |
| live-04 | 47 | 71 | 3/3 words | LLM RECEIVED INPUT |

The `VERDICT` column is the load-bearing output. Without it, the agent
may issue a "Bug X is the cause" report based on the wrong hypothesis.
With it, the agent can cite exactly which tests passed and failed the
gate, and the next agent can reproduce the same gate from the same
trace.

## Pairs with

- `references/hint-injection-test-pattern.md` (v1.7) — the assertion
  pattern for proving a hint reaches the LLM
- The "Memory-cited line numbers and API shapes are not evidence"
  pitfall (SKILL.md v1.8) — the gate produces evidence, not just a
  claim
- The "Amend the live test, don't create a stub-based equivalent"
  pitfall (SKILL.md v1.8) — the gate runs on the live trace, not a
  stub replica
