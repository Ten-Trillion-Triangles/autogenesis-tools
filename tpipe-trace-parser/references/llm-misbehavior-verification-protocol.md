# LLM MISBEHAVIOR Is a Verdict of LAST RESORT

## Why this pitfall exists

TPipe PumpStation has explicit prevention mechanisms for several agent failure modes. The hint-append pattern (turnHistory.add with a [Harness Notice] text) is the canonical prevention layer. When a third-pass triage classifies a finding as "LLM MISBEHAVIOR" without checking whether the prevention mechanism was actually wired, the report misroutes the fix:

- Prevention exists and was triggered → CODE BUG in the prevention code
- Prevention exists and was NOT triggered → CODE BUG in the trigger logic (the prevention is misconfigured or its trigger condition is wrong)
- Prevention does not exist for this failure mode → CODE BUG (missing prevention; not an LLM issue)

Only when all three are ruled out does "LLM MISBEHAVIOR" become a defensible verdict. And even then, the next step is "is this a prompting issue we can harden?" — not "ship as-is."

## The user heuristic

When the operator says "TPipe is designed to prevent this very thing," that is a signal to investigate the prevention layer BEFORE classifying. The operator is asserting an architectural belief about the system. The triage's job is to verify that belief against the source code, not to dismiss it.

If the operator is wrong (prevention does not exist), the triage surfaces that as a finding — "prevention mechanism is missing, this is a feature gap, not a bug." The classification still isn't "LLM MISBEHAVIOR" — it's "MISSING PREVENTION (CODE BUG / feature request)."

## The 3-step pre-classification protocol

Run this BEFORE Step 7 of the PumpStation Third-Pass Triage Protocol (CODE BUG vs LLM MISBEHAVIOR split).

### Step 1: Identify the prevention mechanism the system SHOULD have

For each finding, ask: "What prevention mechanism, if it existed, would have caught this?"

Examples:
- "Dispatch re-picks the same rejected path 6x" → prevention = dispatch prompt should include the rejection verdict
- "Gather produces structured headers when it was supposed to produce raw notes" → prevention = gather system prompt should forbid structured headers
- "Judge says complete when output is malformed" → prevention = judge schema validation on output before isComplete=true is returned

### Step 2: Locate the prevention in the source

Search for the prevention layer:
- Hint-append patterns: `grep -rn "turnHistory.add.*ConverseData.*role.*user" src/main/kotlin/Pipeline/`
- Prompt-level constraints: read the prompt constant (DEFAULT_*_PROMPT in PumpStationDefaults.kt or the test's systemTask/userGuidelines)
- Schema validation: `grep -rn "checkMultimodalFlags\|parseDispatchOutput\|parseJudgeVerdict" src/main/kotlin/Pipeline/`

If the prevention exists, find the trigger site and verify it would have fired in this case.

### Step 3: Classify the actual defect

Three options:

**A. PREVENTION EXISTS AND FIRES** → the finding is misclassified. Re-evaluate. Maybe the prevention text is wrong (CODE BUG in the prompt), maybe the trigger condition doesn't match the failure mode (CODE BUG in the harness logic), maybe the prevention fired but the LLM didn't act on it (PROMPTING ISSUE).

**B. PREVENTION EXISTS BUT DOESN'T FIRE** → CODE BUG. The trigger condition is wrong, the prevention is misconfigured, or it was bypassed. Fix in production source.

**C. PREVENTION DOES NOT EXIST** → CODE BUG / FEATURE GAP. This is a missing prevention layer. The triage report should call this out as "missing hint-append pattern" or "missing prompt constraint" — not "LLM MISBEHAVIOR."

Only after A/B/C are all ruled out does "LLM MISBEHAVIOR" become defensible, and even then it should be tagged as "potential prompting issue — not yet hardened."

## Worked example from 2026-07-08 third-pass triage

Two findings initially classified as LLM MISBEHAVIOR:

### F3: Dispatch re-picks rejected path 6x in stub-07

**Initial classification (WRONG)**: LLM MISBEHAVIOR. Dispatch keeps picking `report` despite 6 consecutive path-safety rejections.

**Step 1 — identify prevention**: The prevention should be a hint appended to turnHistory after path-safety rejection, so the dispatch LLM on turn N+1 sees the rejection verdict in its user prompt. TPipe already has this pattern for empty pathName (PumpStationLoop.kt:378-389), empty rationale (line 2848-2854), and JSON repair failure.

**Step 2 — locate prevention**: Search for turnHistory.add after path-safety rejection:
```
grep -rn "PathSafetyCompleted\|approved.*false" src/main/kotlin/Pipeline/
# Then check each emission site for a turnHistory.add call in the same code block
```
Result: ZERO matches. PathSafetyCompleted emits the event but does NOT append to turnHistory. **The prevention pattern that exists for three other failure modes is missing for this one.**

**Step 3 — reclassify**: PREVENTION DOES NOT EXIST (option C). Re-classify as CODE BUG / FEATURE GAP. The fix is to add a hint-append at the PATH_SAFETY_COMPLETED emission site when approved=false.

**Verdict correction**: F3 is a CODE BUG (missing hint injection), not LLM MISBEHAVIOR. The dispatch LLM behaved correctly given the prompt it received.

### F4: Gather produces "## Finding N" headers instead of raw notes

**Initial classification (WRONG)**: LLM MISBEHAVIOR. M2.7 produced a structured brief when asked for raw notes.

**Step 1 — identify prevention**: The prevention should be a constraint in the gather system prompt forbidding structured headers. The user guidelines already include the constraint ("Brief must mention the topic and contain at least 2 of the 4 required section headers"), but that constraint applies to the REPORT path's output, not the gather path's output.

**Step 2 — locate prevention**: Read the gather system prompt:
```kotlin
// PumpStationMiniMaxLiveTest.kt:787-790
systemPrompt = "You are a research gatherer. Produce 3-5 substantive findings on the topic in the user\'s message. Each finding should be a fact, observation, or tradeoff — not a generic statement. Aim for ~150 words."
```
The prompt says "produce findings." It does NOT say "do not use Markdown headers" or "do not produce a final-form brief." Compare to the report system prompt (line 842-848) which explicitly says "Use these section headers, in this order: ## Overview, ## Tradeoffs, ## Recommendation, ## Sources."

The gather prompt is permissive enough to let M2.7 produce structured output. **The prevention (forbidding structured headers) does not exist in the prompt.**

**Step 3 — reclassify**: PROMPTING ISSUE (with a CODE BUG angle because the prevention layer — the prompt itself — was incomplete). Re-classify as PROMPTING ISSUE, fix class is "tighten gather system prompt to forbid structured headers."

**Verdict correction**: F4 is a PROMPTING ISSUE, not LLM MISBEHAVIOR. The judge correctly caught the violation and re-routed to report, which IS the prevention mechanism working. The 2-turn cost (gather + report) instead of 1 turn (gather alone) is the price of the permissive gather prompt. Adding ~30 chars of constraint to the gather prompt would eliminate the most common prompt-shape flake.

## What to put in the triage report

When this protocol surfaces a reclassification:

1. Update the F-id row in the Bug-Family Summary table to reflect the new category
2. Add a note in the per-finding section explaining the original classification was wrong and why
3. If the finding reveals a missing prevention layer, list it as a separate CODE BUG with file:line of where the prevention SHOULD be wired

Don't silently ship the original "LLM MISBEHAVIOR" classification just because the finding was reported that way. The user's pushback is the prompt to re-verify.

## When the protocol doesn't apply

- Performance findings (slow turn execution, token waste) — not prevention-mechanism-driven
- Transport/HTTP errors (timeouts, EOFException) — not prevention-mechanism-driven
- Stochastic LLM variance within an acceptable range (judge returns slightly different reasons on rerun) — prevention can't help here, this IS LLM variance
- Findings from systems OTHER than PumpStation that don't have the hint-append pattern — check whether THAT system has any prevention layer; if not, this protocol may not be the right frame

## Pairing with other pitfall sections

- v1.4 "Fix claims need source-code evidence" — applies here too: when reclassifying F3 from LLM MISBEHAVIOR to CODE BUG, cite the file:line where the prevention is missing
- v1.5 "Don't write a combined triage report" — Step 7 of the third-pass protocol. This v1.6 protocol runs BEFORE Step 7 to gate whether CODE BUG vs LLM MISBEHAVIOR is even the right split
- "Loop-guard re-select is NOT the bug" (v1.4) — example of a finding that LOOKS like LLM misbehavior but is actually oracle-documented behavior with a sub-bug. Same class of mistake