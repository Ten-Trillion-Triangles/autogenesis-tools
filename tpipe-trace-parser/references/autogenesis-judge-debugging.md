# Autogenesis Judge Trace Debugging

## Overview

When a player claims the judge incorrectly failed to award territory/resources, trace the decision through the pipeline to find which agent reasoning step failed.

## Key Trace Locations

```
~/.tpipe/debug/trace/{TurnFolder}/           # Root turn trace
├── TurnResolutionSplitter/trace.json         # Narrative generation output
├── ValidationSplitter/{timestamp}/
│   ├── railroad/trace.json                   # Railroading detection
│   └── validator/trace.json                 # Action validation
├── Judge/trace.json                          # Judge pipeline (gains/losses + stats)
│   # Sub-pipes within Judge:
│   # - pass or fail pipe: isVictory determination
│   # - gains and losses pipe: territoryGained/lost, assets, stat changes
│   # - explicit cot: chain-of-thought reasoning (structured JSON output)
│   # - resource classification pipe: classifies gained/lost resources
│   # - karma pipe: world karma assessment
│   # - stat change pipe: stat buffs/debuffs
├── WritingAgents/trace.json                 # Narrative writer output
└── AnalysisSplitter/{timestamp}/resources/   # Resource detection
```

## Critical Context: TurnOutcome Injection

In `judge.kt`, the `gainsAndLossesPipe` injects `Turn Outcome: SUCCESS/FAILURE` as a **prefix** to the narrative via `setPreInitFunction`:

```kotlin
val wasSuccessful = readJudgeOutcomeFromContext()
val outcomeString = if(wasSuccessful) "Turn Outcome: SUCCESS" else "Turn Outcome: FAILURE"
it.text = "$turnTypePrefix$summitRulesPrefix$outcomeString\n\n${it.text}"
```

This means the gains/losses agent receives the outcome as context — it doesn't determine success/failure, it just reacts to it.

The `TurnOutcome` comes from `passOrFailPipe` which writes `isVictory` to `ContextBank` under `JUDGE_OUTCOME_CONTEXT`.

## Finding the Root Cause of Wrong Decisions

### Pattern: territoryGained is empty but should have territory

1. **Find the gains/losses result**: In `Judge/trace.json`, search for `resultSummary` with `"territoryGained": []` in the gains/losses pipe output.

2. **Extract the explicit CoT reasoning**: The explicitCoT pipe outputs structured JSON with `coreAnalysis`, `logicalBreakdown`, and `sequentialReasoning`. Look for `API_CALL_SUCCESS` events where `pipeName` is `explicit cot`. The CoT reasoning is in `recommendedSteps`.

3. **Identify the reasoning failure**: The CoT agent often reaches the wrong conclusion by asking the wrong question. Example — it asked "does the narrative say 'capture'?" instead of "do automatic capture rules apply?"

### Example: Lord Maple Tree (Round 1 Turn 0)

**Narrative said**: "Lord Maple Tree's forces advanced unopposed."

**What the CoT agent did**: Searched for explicit capture language like "conquered", "captured", "annexed". Found none → `territoryGained: []`.

**What it should have done**: Applied automatic capture rule — "forces advanced unopposed" = Decisive Battle Victory = automatic capture. No explicit capture language needed.

**The bug**: The CoT reasoning prompt tells the agent to check for "explicit capture language" but the automatic capture rules (in `judge.kt` lines 764-780) state that capture is **automatic** when conditions are met, regardless of explicit language.

### Key Code Reference

`judge.kt` automatic capture rules (lines 764-780):
```
1. Decisive Battle Victory: Player wins, enemy is defeated/retreats/surrenders, 
   Player's forces control battlefield at battle's end
2. Territory Held: Player captures ANY portion AND holds it by turn's end
```

The agent should apply these BEFORE searching for explicit capture statements.

## Debugging Commands

```bash
# Find territoryGained results in a large trace
python3 -c "
import json
with open('/path/to/Judge/trace.json') as f:
    events = json.load(f)
for i, e in enumerate(events):
    content = e.get('content', {})
    if content and 'text' in content:
        text = content['text']
        if '\"territoryGained\"' in text and 'resultSummary' in text:
            print(f'Event {i}: {e.get(\"eventType\")}')
            print(text[:1500])
            print('---')
"

# Find the explicit CoT reasoning output
python3 -c "
import json
with open('/path/to/Judge/trace.json') as f:
    events = json.load(f)
for i, e in enumerate(events):
    content = e.get('content', {})
    if content and 'text' in content:
        text = content['text']
        if '\"recommendedSteps\"' in text or '\"sequentialReasoning\"' in text:
            print(f'Event {i}: {e.get(\"eventType\")} | {e.get(\"pipeName\")}')
            print(text[:2000])
"

# Find where TurnOutcome was injected
python3 -c "
import json
with open('/path/to/Judge/trace.json') as f:
    events = json.load(f)
for i, e in enumerate(events):
    content = e.get('content', {})
    if not content: continue
    text = content.get('text', '')
    if 'Turn Outcome: SUCCESS' in text or 'Turn Outcome: FAILURE' in text:
        print(f'Event {i}: {e.get(\"eventType\")} | {e.get(\"pipeName\")}')
        idx = text.find('Turn Outcome')
        print(text[idx:idx+50])
"
```

## Common Failure Patterns

1. **CoT searches for wrong thing**: Agent looks for explicit "capture/conquer/annex" instead of applying automatic capture rules
2. **Narrative Override not triggered**: The NARRATIVE OVERRIDE RULE says definitive narrative statements MUST be dispatched, but the agent misses definitive statements hidden in verbose prose
3. **Reversal story detection too aggressive**: Lines 682-712 check for "failed to", "did not", "invasion failed" — but these can appear in satirical/absurdist writing that isn't actually a reversal
4. **Loss conditions checked before win conditions**: The flowchart checks loss conditions first — if the agent incorrectly identifies a loss condition, it stops there without evaluating wins

## Known Autogenesis Trace Paths

| Game Event | Trace Path |
|------------|------------|
| Lord Maple Tree's first turn | `Round_1_Turn_0_Lord_Maple_Tree/Judge/trace.json` |
| Turn narrative output | `TurnResolutionSplitter/narrative/trace.json` |
| Action validation | `ValidationSplitter/{timestamp}/validator/trace.json` |
| Railroading check | `ValidationSplitter/{timestamp}/railroad/trace.json` |
| Resource detection | `AnalysisSplitter/{timestamp}/resources/trace.json` |