---
name: tpipe-trace-parser
title: TPipe Trace Parser — verified ground-truth extraction
description: "Parse TPipe trace artifacts (HTML and JSON) into structured events, accurate token totals, per-pipe and per-event-type aggregates. Triggers on: parse trace, trace tokens, trace events, trace triage, debug trace, what's the actual token count, per-pipe breakdown, ground-truth extraction, Layout B container reports."
author: Apex (TTT)
created: 2026-07-24
version: 3.4
changelog:
  3.4.0: "Two new pitfalls (2026-07-25 autogenesis margin-report v3 session). #1: 'two trace directories exist — one is contaminated, the other is clean' — ~/.tpipe/autogenesis-trace/ is bugged (music-injection era); ~/.tpipe/debug/trace/ is trustworthy. Detection recipe + cross-reference to audio-injection-pattern.md. #2: 'extract_pipeline.py --tokens-only references files_scanned after stripping it (KeyError)' — the --tokens-only rebuild forgets fields that print_summary reads; fix at lines 306-313 with all the fields print_summary needs. Also: token taxonomy 'Critical distinction' rewritten to cite TPipe source (Pipe.kt:220-256, Pipe.kt:6442-6453, BedrockPipe.kt:4035) and pin inputTokens (provider-billed) as the canonical billing truth — overriding the prior v3.3 framing that pointed at actualInputTokens."
  3.3.0: "Pitfall added: 'a derived artifact (PDF / dashboard / pricing model) shipped on the wrong bucket'. Captures the 2026-07-25 autogenesis margin-report v1 -> v2 failure where a 30-page pricing PDF was built on totalInputTokens (cumulative bucket) instead of inputTokens (per-call bucket), inflating per-turn cost by ~2.4x ($0.32 hallucinated vs $0.0966 actual). The fix is the explicit cross-validation table that must be filled from a fresh extract_pipeline.py run before shipping any derived artifact."
  3.2.0:
tags: [tpipe, trace, parser, html, json, tokens, triage, debug, ground-truth, verification, autogenesis, geoplitics, round-capture]
trigger: When reading TPipe trace files (HTML or JSON), computing token totals, auditing event streams, building per-pipe/per-event-type aggregates, validating that an extraction matches ground truth, OR when asked about the token cost of an Autogenesis round-level capture (geoplitics, Overton window, any "once per round" content). For round-level capture specifically, see `references/autogenesis-round-level-capture.md` — the producer pipes are per-player `Synthesis Stage (<Name>)`, not the literal `geoPolitics` pipe name (which doesn't exist). Load BEFORE writing any script that touches trace artifacts.
---

# TPipe Trace Parser — verified against ground truth

## The rule

**Every extraction of trace data MUST go through `parse_html_trace.py` (HTML) or `parse_json_trace.py` (JSON), and any custom extraction MUST pass `verify_extraction.py --strict` against the seven pinned cases before being trusted.**

The previous version of this skill shipped parsers that returned wrong numbers — concatenated metadata strings, missing fields, false totals, and length-vs-token confusion. The current parsers are verified against ground truth extracted directly from raw HTML/JSON by independent regex. Run `verify_extraction.py --strict` to confirm a clean baseline before trusting anything they emit.

```
Ran 7 case(s); 0 failure(s)
exit: 0
```

## What's actually in a TPipe trace file

Two formats, both produced by `TraceVisualizer.kt` and stored under `${TPipeConfig.getTraceDir()}/`:

### HTML format (container reports)

```
<!DOCTYPE html>
<html>
<head>
    <title>PumpStation Trace — ps-1784931031776-5154</title>  ← run_id
    <style>...CSS with .ps-* or .trace-* classes...</style>
</head>
<body>
    <!-- Standard pipeline / Manifold / Junction / Splitter / DistributionGrid:
         <table id="trace-details-table">
           <tr id="trace-event-N" class="trace-item" data-pipe="judge">
             <td>+0ms</td>                                ← elapsed
             <td>judge</td>                               ← pipeName
             <td>PIPE_START</td>                          ← eventType
             <td>INITIALIZATION</td>                      ← phase
             <td class="info">ℹ️ INFO</td>                ← status (class attr is the source of truth)
             <td class="metadata">                        ← metadata cell
                 <strong>key1:</strong> val1<br>
                 <strong>key2:</strong> <span style="color: #28a745;">1705</span><br>
                 <details><summary>📥 Input Content (7170 chars)</summary><pre>...</pre></details>
             </td>
           </tr>
         </table>

    <!-- PumpStation (generatePumpStationHtmlReport):
         <details class='ps-turn-card'>
           <summary>
             <span class="ps-status ps-status-completed">COMPLETED</span>
             <span class="ps-run-id">ps-1784931031776-5154</span>
             <span class="ps-duration">⏱ 93845ms</span>
             <span class="ps-turn-num">Turn 0</span>
             <span class="ps-phase-pill ps-phase-success">Judge completed</span>
             ...
           </summary>
           <div class='ps-turn-body'>
             <div class='ps-detail-row'>
               <div class='ps-detail-label'>Started <span class='ps-detail-type'>(PUMP_STATION_STARTED)</span></div>
               <div class='ps-detail-meta'>
                 <div class='ps-meta-row'>
                   <span class='ps-meta-key'>originalInputPreview:</span>
                   <span class='ps-meta-val'>Research: Kotlin coroutines...</span>
                 </div>
                 <div class='ps-meta-row'>
                   <span class='ps-meta-key'>inputTokens:</span>
                   <span class='ps-meta-val'>1928</span>
                 </div>
               </div>
             </div>
             <details class='ps-event-extras'>
               <summary>📝 contentPreview</summary>
               <pre class='ps-event-text'>...long content...</pre>
             </details>
           </div>
         </details>
    -->
</body>
</html>
```

**The single-quote vs double-quote gotcha**: PumpStation uses `class='ps-detail-label'` (single) for some elements and `class="ps-run-id"` (double) for others. Every regex uses `class=['\"]...['\"]` to handle both.

### JSON format

`List[TraceEvent]` serialized by kotlinx-serialization + MapAnySerializer:

```json
[
    {
        "id": "trace-event-1047",
        "timestamp": 1784845644440,
        "pipeId": "uuid",
        "pipeName": "reversal-pipe",
        "eventType": "API_CALL_SUCCESS",
        "phase": "EXECUTION",
        "content": { "text": "...", "binaryContent": [...] } | null,
        "contextSnapshot": {...} | null,
        "metadata": {
            "inputTokens": 1705,            ← native int
            "outputTokens": 311,
            "totalTokens": 2016,
            "actualInputTokens": 2328,     ← model-reported prompt tokens (incl. reasoning)
            "reasoningTokens": 203,
            "responseLength": 561,
            "reasoningLength": 1081,
            "model": "MiniMax-M2.7",
            "apiType": "ResponsesAPI",
            "responseId": "06b315d1378376c41a3c47ce4af10b6e",
            ...
        }
    },
    ...
]
```

**`@Transient error: Throwable?` is NOT serialized.** If you see error info in metadata, it was lifted into a key by the producer (e.g. `errorMessage`).

**`MapAnySerializer.deserialize` is write-only lossy** (`mapValues { it.value.toString() }`). Decoding a `metadata` value back to typed integers requires `int(v)` conversion in Python — see `parse_json_trace.py:_coerce_int`.

## The script inventory (verified)

Every script below passes `verify_extraction.py --strict` against the seven pinned cases.

| Script | Purpose | Verified outputs |
|--------|---------|------------------|
| `parse_html_trace.py` | Parse any container HTML trace → structured events + token totals + length totals | 7/7 PASS |
| `parse_json_trace.py` | Parse `List[TraceEvent]` JSON → events + tokens + per_pipe + per_event_type | 7/7 PASS |
| `extract_pipeline.py` | End-to-end: walk a directory, parse every file, aggregate across all | 7/7 PASS, sum-cross-checked |
| `verify_extraction.py` | Self-test: ground-truth case fixtures vs parser output (7 pinned cases + 61 autogenesis JSON stress test) | 7/7 PASS at v3.1 |

## How to extract token totals (the operator's most common ask)

```
# Single file, full output
python3 scripts/parse_html_trace.py --input path/to/trace.html --output parsed.json

# Single file, token totals only (terse)
python3 scripts/parse_html_trace.py --input path/to/trace.html --format tokens

# Single file, one-line-per-event summary
python3 scripts/parse_html_trace.py --input path/to/trace.html --format summary

# Directory of traces (the live-test case)
python3 scripts/extract_pipeline.py --dir /home/cage/.tpipe/debug/trace/some-test/
python3 scripts/extract_pipeline.py --dir /path --tokens-only           # aggregate only
python3 scripts/extract_pipeline.py --dir /path --filter pumpstation    # restrict format

# JSON traces
python3 scripts/parse_json_trace.py --input path/to/trace.json --format tokens
python3 scripts/parse_json_trace.py --input path/to/trace.json --format tokens_and_lengths
python3 scripts/parse_json_trace.py --input path/to/trace.json --format per_pipe
```

The `--format` flag picks an output shape. Format availability is parser-specific: `parse_json_trace.py` accepts `full`, `tokens`, `tokens_and_lengths`, `per_pipe`, `per_event_type`, and `events`; it does not accept `timeline` or `summary`.
- `tokens` — only `token_totals` aggregate (`{"inputTokens": {"total": N, "count": N}, ...}`)
- `tokens_and_lengths` — `token_totals` + `length_totals` side-by-side (the canonical "what did we spend" view)
- `timeline` — HTML parser only; chronologically-ordered events with key fields surfaced (`selectedPathName`, `pathName`, `riskLevel`, `isComplete`, `shouldTerminate`, `exitReason`, `judgeRunMode`, etc.)
- `summary` — HTML parser only; one-line-per-event, condensed, human-readable
- `per_pipe` / `per_event_type` — JSON only, aggregation by pipe or by event type
- `events` — JSON only, simplified events with long strings truncated
- `full` — complete dump

## Token field taxonomy (the actual keys the system emits)

After stress-testing against 61 autogenesis JSON traces + 10 PumpStation HTML traces, the canonical taxonomy is split into two buckets. Tokens and character lengths are NOT interchangeable — a `responseLength` of 5000 is 5000 characters, NOT 5000 tokens.

### TOKEN keys (semantically equivalent to LLM tokens — what billing uses)

| Key | Where emitted | Meaning |
|-----|---------------|---------|
| `inputTokens` | API_CALL_SUCCESS, JUDGE_COMPLETED, DISPATCH_COMPLETED, PATH_COMPLETED | Prompt tokens sent (may include reasoning prefix in Reasoning models) |
| `outputTokens` | same | Tokens generated |
| `totalTokens` | same | `inputTokens + outputTokens` (always equal to sum when both present) |
| `actualInputTokens` | CONTEXT_PREPARED (standard pipeline only) | Real model-reported prompt tokens after server-side counting |
| `reasoningTokens` | API_CALL_SUCCESS (when `modelSupportsReasoning && reasoningEnabled`) | Tokens used by chain-of-thought reasoning |
| `totalInputTokens` / `totalOutputTokens` | some Pipe implementations | Aggregate across retries / multi-shot calls |

### LENGTH keys (character counts — NOT tokens)

| Key | Where emitted | Meaning |
|-----|---------------|---------|
| `responseLength` | API_CALL_SUCCESS | Character length of response text |
| `resultTextLength` | some JSON traces (autogenesis) | Character length of result content |
| `resultLength` | some JSON traces | Character length of validation result |
| `reasoningLength` | API_CALL_SUCCESS | Character length of reasoning text |
| `promptLength` | API_CALL_START | Character length of prompt sent |

**Rule: never aggregate lengths into token totals.** The parser reports `token_totals` and `length_totals` separately. A `responseLength` of 5000 in a token total means the parser is wrong (it was reporting characters as tokens), not that the model spent 5000 tokens.

**Critical distinction (per TPipe source — Pipe.kt:220-256, Pipe.kt:6442-6453, BedrockPipe.kt:4035):**
- `inputTokens` (from provider parsers — BedrockPipe.kt:4035, OpenRouterPipe.kt:728, model-specific parsers at BedrockPipe.kt:4789-4810) = the API-reported billed value, populated from the vendor's usage block (`prompt_tokens` / `input_tokens` / `promptTokens` depending on provider). **This is the canonical billing truth.**
- `actualInputTokens` (from `Pipe.kt:6442`, emitted on `CONTEXT_PREPARED`) = TPipe's pre-call local estimate via `countActualInputTokens()` (Pipe.kt:7770-7807) which uses `Dictionary.countTokens` on the finalized prompt. Gated on `comprehensiveTokenTracking`. Pre-flight billing estimate, useful for spotting truncation bugs. NOT the bill.
- `totalInputTokens` (from `TokenUsage.recalculateTotals()` at Pipe.kt:249-256) = this pipe's `inputTokens` plus the sum of every child pipe's `totalInputTokens`, recalculated whenever a child is added. Recursive aggregate across reasoning + validator + main pipes. End-of-pipeline cost rollup number. NOT additive with `inputTokens`.
- `reasoningTokens` (from `API_CALL_SUCCESS` when `modelSupportsReasoning && reasoningEnabled`) = a SUBSET of `actualInputTokens` for reasoning-capable models — what the model spent thinking before producing output.

**Important quirk:** when `comprehensiveTokenTracking` is OFF, `pipeTokenUsage.inputTokens` stays at 0. The pipeline still tracks aggregate usage via the simpler `pipelineRef.inputTokensSpent` path, which KillSwitch and cross-pipeline cost reporting use in that mode. Verify the gating before assuming `inputTokens` will be present on every `API_CALL_SUCCESS`.

**For any cost/pricing derivation:** use `inputTokens` (provider-billed). It is the only field that reflects what the upstream model provider charged. The other fields are pre-flight estimates and recursive aggregates — useful for their own diagnostics, but mixing them with `inputTokens` in a sum is double-counting.

When in doubt, use `inputTokens` for billing.

## Why the previous parsers were wrong

The previous `parse_html_trace.py` had three classes of bugs:

1. **Metadata concatenation** — used `<strong>([^<]+)</strong>:\s*([^\n<]+)` which captured up to the next `<`, causing every key to grab all subsequent keys' values. Result: `actualInputTokens: 2328pipeClass: genericOpenAIPipe...`
2. **Status always UNKNOWN** — `extract_status(class_attr)` was correct logic but never called because cell attrs weren't extracted.
3. **Missing `data-pipe`** — every event's pipeName showed up as `judge` because the row attribute wasn't parsed.

The previous `parse_pumpstation_html.py` was correct for the HTML structure on one trace but:
1. **Brittle** — single-quote-only regex (`class='ps-detail-label'`) broke on double-quoted `class="ps-run-id"` elements.
2. **No turnIndex** — never surfaced which turn an event belonged to.
3. **Token totals missing** — didn't aggregate tokens across events.

The previous `parse_json_trace.py`:
1. **Did not preserve token counts correctly** — read `metadata[k]` as the raw value but didn't normalize scalars vs nested dicts.
2. **No aggregation** — caller had to sum tokens manually.
3. **Recovery regex unsafe** — `try_recover_json` could find a `{}` inside a string and treat it as the root.
4. **Tokens vs lengths conflated** — `responseLength` (character count) was rolled into the same bucket as `inputTokens` (token count). The 56-of-61 autogenesis traces flagged this on first stress test.

The current parsers fix all of these.

## Workflow: trace triage in 5 steps

1. **Locate** — find the trace dir (usually under `~/.tpipe/debug/trace/<test-name>/`).
   ```bash
   ls /home/cage/.tpipe/debug/trace/
   ```
2. **Aggregate** — run `extract_pipeline.py` to get the cross-file summary.
   ```bash
   python3 scripts/extract_pipeline.py --dir /home/cage/.tpipe/debug/trace/<test-name>/
   ```
   Look at `aggregate_token_totals` and `format_breakdown` first. The total counts (e.g. `inputTokens.count`) tell you how many events carried tokens — if zero, your parser ran but the source didn't emit any.
3. **Drill** — pick a single trace file and run `--format summary` to see the event stream.
   ```bash
   python3 scripts/parse_html_trace.py --input /path/to/pumpstation-ps-XXXX.html --format summary
   ```
4. **Inspect** — for an event of interest, run `--format full` and look at `events[i].metadata` + `events[i].contentBlocks`.
   ```bash
   python3 scripts/parse_html_trace.py --input trace.html --output full.json
   jq '.events[5].metadata' full.json
   jq '.events[5].contentBlocks[0].text' full.json
   ```
5. **Validate** — before trusting any new extractor, run `verify_extraction.py --strict`.
   ```bash
   python3 scripts/verify_extraction.py --strict
   ```
   Should print `Ran 7 case(s); 0 failure(s)` and exit 0.

## Workflow: capturing a new ground-truth case

When you discover a new trace format variant (e.g. a new container adds a new event class), capture it as a pinned case so future regressions are caught:

```bash
python3 scripts/verify_extraction.py --add my-new-case /path/to/new-trace.html
```

This prints a JSON snippet you paste into the `CASES` dict in `verify_extraction.py`. The script then runs every time `--strict` is invoked and flags drift.

## Workflow: parsing JSON traces (autogenesis / older tests)

Some directories contain `trace.json` files (autogenesis, older test outputs):

```
~/.tpipe/autogenesis-trace/Round_*/Turn_*/AgentName/trace.json    ← List[TraceEvent]
~/.tpipe/debug/trace/<test>/pumpstation-ps-*.html                 ← HTML report
```

Use `parse_json_trace.py --format per_pipe` to break token spend down by pipe name. Example output:

```json
{
  "reversal-pipe": {"event_count": 17, "event_types": [...], "tokens": {...}},
  "structured cot": {"event_count": 24, "event_types": [...], "tokens": {...}},
  "validator-pipe": {"event_count": 13, "event_types": [...], "tokens": {...}}
}
```

This is the right shape for "which pipe burned the budget" triage.

## Cross-validation invariants

These invariants hold for the current parsers and any new parser must preserve them:

1. **Sum of per-pipe tokens equals aggregate token totals** (cross-checked in `extract_pipeline.py:print_summary`).
2. **Sum of per-event-type tokens equals aggregate token totals**.
3. **`totalTokens` (when present) equals `inputTokens + outputTokens`** for the same event.
4. **`event_count` matches the count of `<tr class="trace-item">` rows in standard-pipeline HTML** and **the count of `<div class='ps-detail-label'>` blocks in pumpstation HTML**.
5. **Event-type ordering is preserved** from source HTML to parser output (chronological).
6. **`run_id` for PumpStation matches `<title>...ps-NNNN</title>`** AND `<span class="ps-run-id">ps-NNNN</span>` (parser uses title as fallback if class is absent).
7. **`token_totals` keys are a strict subset of TOKEN_KEYS** (`inputTokens`, `outputTokens`, `totalTokens`, `actualInputTokens`, `reasoningTokens`, `totalInputTokens`, `totalOutputTokens`). Length keys never appear in `token_totals`.
8. **`length_totals` keys are a strict subset of LENGTH_KEYS** (`responseLength`, `reasoningLength`, `promptLength`, `resultLength`, `resultTextLength`). Token keys never appear in `length_totals`.

## Pitfalls

### Pitfall: HTML uses BOTH single and double quotes

```html
<div class='ps-detail-label'>...TYPE...</div>     <!-- single quotes -->
<span class="ps-run-id">ps-NNNN</span>           <!-- double quotes -->
```

Every regex uses `class=['\"]...['\"]` to handle both. Don't optimize for one style — the same file uses both.

### Pitfall: Junction/Manifold/DistributionGrid use Layout B (NOT Layout A)

Container HTML reports use `<article class="trace-item event-card">` with `<header class="event-header">` containing status badges — completely different from standard pipeline `<tr><td>` rows. The previous parser returned 0 events for every container trace because it only matched `<tr class="trace-item">`. See `references/html-layout-b-containers.md` for the full regex set. Detection must use title-based matching (`<title>TPipe Junction Execution Analysis</title>`), not substring-on-first-5KB. Both layouts can coexist in one container's trace tree (the container emits Layout B, its nested pipes emit Layout A as row tables).

### Pitfall: pumpstation meta uses trailing colon, standard pipeline doesn't

```html
<!-- PumpStation -->
<span class='ps-meta-key'>inputTokens:</span>      ← trailing colon

<!-- Standard pipeline -->
<strong>inputTokens:</strong>                       ← also trailing colon
```

Both emit `:`, so both regexes match `<key>:</...>`. The parser strips trailing colons from keys when emitted to JSON.

### Pitfall: token field appears MULTIPLE times with different scopes

In a single API_CALL_SUCCESS row in standard pipeline, you may see:
- `inputTokens` (the prompt token count)
- `actualInputTokens` (model-reported, more accurate)
- `totalInputTokens` (cumulative across the run)

These are NOT redundant — they represent different scopes. Don't collapse them.

### Pitfall: standard_pipeline HTML has TWO API_CALL_SUCCESS events per Pipe

Per Pipe, the visualizer emits:
1. **First** API_CALL_SUCCESS with `inputTokens/outputTokens/totalTokens` — the prompt/response/token counts.
2. **Second** API_CALL_SUCCESS with `totalInputTokens/totalOutputTokens` — cumulative totals for the entire pipeline run.

These two events are emitted with the SAME event type but DIFFERENT metadata. The parser captures both; callers should know that `outputTokens` count will be ~2× expected if you're naively summing across all API_CALL_SUCCESS events for a single pipe run.

### Pitfall: token field `count` ≠ event count

`token_totals[k].count` is the number of EVENTS that emitted that key, not the number of unique values. A 3-turn PumpStation emits 9 JudgeCompleted events with `totalTokens` → `count=9`. If you want "total tokens spent across all turns", use `token_totals[k].total`.

### Pitfall: responseLength is NOT a token count

The previous version of this skill conflated character lengths with token counts. `responseLength=5000` means the response text was 5000 characters, NOT 5000 tokens. A typical 5000-char response is ~1250 tokens (4 chars/token for English). The parser now reports `token_totals` and `length_totals` separately — never mix them.

### Pitfall: grep -oE ".{0,N}" HANGS on long single-line trace HTML

Each event block is one HTML line, 1500-1700 chars typical. Greedy `.{0,1500}` triggers catastrophic backtracking (15-30s hangs). Use negated char class `[^\"]{0,1500}` for <100ms. (From `tpipe-trace-output-conventions` skill — applies here too.)

### Pitfall: `MapAnySerializer.deserialize` is lossy

You CANNOT round-trip a metadata map from JSON back to typed values. The Kotlin source at `Debug/TraceEvent.kt:89` does `mapValues { it.value.toString() }` on decode. If you read a JSON trace file, token values come back as ints (because kotlinx-serialization preserves scalar types) — but complex nested maps come back as `Map<String, JsonElement>`. The parser handles both.

### Pitfall: two trace directories exist — one is contaminated, the other is clean

TPipe writes trace artifacts to two distinct locations, and only ONE of them is trustworthy after the music-injection bug era. The two directories:

| Directory | What lives here | Trustworthy? |
|-----------|----------------|--------------|
| `~/.tpipe/autogenesis-trace/Round_*_Turn_*` | autogenesis game traces — captured by `agent/debugTrace/*` instrumentation at runtime | **NO** — captured while the audioTracks world-snapshot bug was active; tokens inflated ~2x. Per operator (2026-07-25): "they are bugged if you recall due to the music bug, ignore these." |
| `~/.tpipe/debug/trace/<test-name>` | live-test traces — captured by `TPipeConfig.getTraceDir()` (PumpStation, Manifold, Junction, DistributionGrid) | **YES** — captured by the post-fix `TraceVisualizer.kt` path |

**The trap.** A future session that needs autogenesis-game token data will find `~/.tpipe/autogenesis-trace/` and walk it without questioning. The traces look structurally valid (correct schema, sensible bucket ratios, plausible event counts) — but every `inputTokens` value is inflated by the audio-injection pattern documented in `references/audio-injection-pattern.md`.

**Detection.** Run `extract_pipeline.py` on both directories and compare:

```bash
# Trustworthy (live tests)
python3 scripts/extract_pipeline.py --dir ~/.tpipe/debug/trace/Round_3_Turn_0_Lord_Maple_Tree --output /tmp/clean.json
# Contaminated (autogenesis game)
python3 scripts/extract_pipeline.py --dir ~/.tpipe/autogenesis-trace/Round_1_Turn_0_Lord_Maple_Tree --output /tmp/buggy.json
```

If the autogenesis-game per-call input tokens per human turn are 2-3x the live-test per-call input tokens per human turn (matching player archetype), the autogenesis directory is contaminated. Use the live-test data, not the autogenesis-game data, for any token-derived artifact (pricing, cost projections, MAU math).

**The fix.** If autogenesis-game traces are needed for a specific analysis, run a fresh autogenesis game session with trace capture AFTER confirming the audio-injection fix is deployed. The new trace directory will be `~/.tpipe/debug/trace/<session-id>/` (the live-test path) or a dedicated trace dir set via `TPipeConfig.getTraceDir()` override. The autogenesis-game path is contaminated until a clean replay lands.

**Cross-reference.** See `references/audio-injection-pattern.md` for the root cause (consumer-side world-snapshot serializer at `WorldTokenTrace.kt:156` pulling the full audio catalog into every prompt). The directory distinction is the operational expression of that root cause — until a fresh post-fix replay, autogenesis-game traces are unusable for token-derived artifacts.

### Pitfall: `extract_pipeline.py --tokens-only` references `files_scanned` after stripping it (KeyError)

The `--tokens-only` flag in `extract_pipeline.py` rebuilds the report dict with only the aggregate fields, but it forgets to keep `files_scanned`, `files_failed`, and `run_statuses`. Then `print_summary()` reads `report['files_scanned']` and crashes:

```
Traceback (most recent call last):
  File "extract_pipeline.py", line 327, in <module>
    sys.exit(main())
  File "extract_pipeline.py", line 315, in main>
    print_summary(report)
  File "extract_pipeline.py", line 265, in print_summary
    print(f"  files: scanned={report['files_scanned']} parsed={n} failed={len(report['files_failed'])}", file=stream)
KeyError: 'files_scanned'
```

**Trigger.** Any agent session that runs `python3 scripts/extract_pipeline.py --dir <path> --tokens-only` to grab just the token totals without the verbose per-file dump.

**The fix (already shipped at lines 306-313 of extract_pipeline.py):** keep the fields `print_summary` reads.

```python
if args.tokens_only:
    report = OrderedDict([
        ("dir", report["dir"]),
        ("files_scanned", report["files_scanned"]),
        ("files_parsed", report["files_parsed"]),
        ("files_failed", report["files_failed"]),
        ("format_breakdown", report["format_breakdown"]),
        ("run_statuses", report["run_statuses"]),
        ("aggregate_token_totals", report["aggregate_token_totals"]),
    ])
```

**Detection.** Run `python3 scripts/extract_pipeline.py --dir <path> --tokens-only --quiet` once on any directory that has at least one file. If `files_scanned` isn't in the output JSON, the bug is back. The script never invoked this path until a 2026-07-25 session; future regressions will reintroduce the strip because the `--tokens-only` block is a temptation for "less is more" cleanup.

**Why this trap is hard to spot.** The default path (no `--tokens-only`) works fine — `print_summary` reads the full `build_report()` output. The bug is reachable only via the `--tokens-only` flag, which most agents hit when they want a quick "what's the token total" answer without a 200KB JSON dump. When the agent is doing its first trace extraction in a session, the parser self-test is the right place to catch this. The seven pinned verification cases don't cover `--tokens-only`, so this would slip past `verify_extraction.py --strict`.

**Coverage gap.** The verification suite tests parsing output, not flag combinations. Before any future flag addition to `extract_pipeline.py`, the test should include a smoke test of the flag combination against any sample directory.

### Pitfall: a derived artifact (PDF / dashboard / pricing model) shipped on the wrong bucket

The trap: someone built a downstream artifact — a pricing PDF, a margin model, a dashboard panel — by summing across trace events using the WRONG bucket (typically `totalInputTokens` thinking it's per-call). The artifact looks plausible, the totals are in the same order of magnitude as reality, and the divergence isn't visible without re-extracting the same traces from scratch. The bucket-confusion survives until a fresh round of traces exposes the inflation.

**Confirmed failure (2026-07-25, autogenesis margin report v1 → v2):** The v1 PDF claimed $4.31/game @ E[12 rounds] based on `totalInputTokens` summed across 4 turn directories — but `totalInputTokens` is the CUMULATIVE bucket and `inputTokens` is the per-call bucket. The v1 totals were inflated by ~2.4×. The per-turn cost was hallucinated as $0.32 when the real number was $0.0966. The PDF was 30 pages long with charts, projections, and tier-margin tables all derived from the inflated numbers. The number only got caught when the user asked for a re-build grounded in real trace data.

**The rule.** Before publishing ANY derived artifact (PDF, dashboard, report, pricing model, executive summary) that depends on trace-token data:

1. **Pin the bucket choice in writing.** If the artifact uses `totalInputTokens`, say so. If it uses `inputTokens`, say so. Never mix.
2. **Cross-check the per-event count against the bucket count.** `token_totals[k].count` is the number of EVENTS that emitted that key. A 4-turn autogenesis game with ~3,845 model calls has `inputTokens.count ≈ 900-1000` (per-call) but `totalInputTokens.count ≈ 1000` ALSO at the per-call level (one emission per call). Summing `inputTokens.total + totalInputTokens.total` gives double-counting. The test: if your "total tokens across N turns" is within 1.5× of "totalInputTokens.total across N turns", you're probably double-counting.
3. **Walk every trace.json yourself, once, on a fresh extraction.** Don't trust derived tables — re-extract with the parser, then sanity-check the totals match what the artifact claims. The verification step is `python3 scripts/extract_pipeline.py --dir <dir> --output full.json` → read `aggregate_token_totals.inputTokens.total` and compare against the artifact's headline number. If they diverge by more than 10%, the artifact is wrong.

**Detection heuristic before publishing any derived artifact:**

```bash
# Pin the bucket and re-extract
python3 scripts/extract_pipeline.py --dir <trace-dir> --output /tmp/verify.json
# Read these two values:
python3 -c "import json; r=json.load(open('/tmp/verify.json')); print('per-call input:', r['aggregate_token_totals']['inputTokens']['total']); print('cumulative totalInput:', r['aggregate_token_totals']['totalInputTokens']['total'])"
# The cumulative value should be 1.0x-1.6x the per-call value (the ratio is the per-call emissions that include a cumulative tracker). If the artifact claims a number ABOVE the cumulative, the artifact is hallucinating.
```

**The cross-validation table to include in the artifact itself.** When shipping any pricing/cost derived from traces, include a "what changed vs. last version" table with one row per token bucket:

| Metric | v1 claim | v2 (ground truth) | Source |
|--------|----------|-------------------|--------|
| Avg input tokens / turn | X | Y | `extract_pipeline.py` per-call bucket |
| Avg output tokens / turn | X | Y | same |
| Avg cost / turn | X | Y | walked trace.json · per-model rates |

If you can't fill that table from a fresh `extract_pipeline.py` run, the artifact isn't grounded. Don't ship it.

**Why this trap recurs across sessions.** The token-bucket disambiguation is in the skill body (Token field taxonomy table), but the table is the only place it's documented. Agents skim it, pick the first bucket they see, and don't realize they're on cumulative vs. per-call. The 2.4x inflation is invisible until the user asks for a re-build. The fix is the explicit cross-validation table above and the "walk every trace.json yourself" rule.

**Symptom.** A previously-shipped PDF/report/dashboard claims per-turn cost in the $0.20-$0.50 range and total input tokens per turn in the ~800K-1M range. A fresh `extract_pipeline.py` run on the same trace directory returns per-call input tokens in the ~1.5M-2.5M range and per-turn cost in the $0.05-$0.15 range. The artifact was using cumulative buckets. Re-extract, re-publish.

### Pitfall: existing parsers looked "verified" on one trace file but failed on the next 60

The earlier verification suite pinned ONE HTML trace per format. Real bugs hid in autogenesis JSON traces (61 of them) where `responseLength` was a character count but the parser treated it as tokens. The fix: stress-test against EVERY trace file on disk, not just a hand-picked sample. `verify_extraction.py --strict` covers the pinned 7; to stress-test against all autogenesis JSON traces, run:

```bash
for f in $(find ~/.tpipe/autogenesis-trace -name 'trace.json'); do
    python3 scripts/verify_extraction.py --case $(basename $f)  # add --add NAME PATH first
done
```

Or use the `~/bin/stress-test-parsers.sh` script in `scripts/` to run the full sweep.

## Verification suite (the ten pinned cases)

These cases are the floor. If a future change breaks any of them, the script returns exit code 1 and prints the diff. The suite covers every format family — PumpStation, Junction, DistributionGrid, Manifold, standard pipeline, and JSON — with at least one case per family.

| Case | Format | Path | Expected | Verified |
|------|--------|------|----------|----------|
| pumpstation-interrupt | pumpstation | `~/.tpipe/debug/trace/tpipe-config-interrupt-live/pumpstation-ps-178493309.html` | 13 events, 3338/461/3799 tokens | ✓ |
| pumpstation-steering | pumpstation | `~/.tpipe/debug/trace/tpipe-config-steering-live/pumpstation-ps-178493312.html` | 31 events, ≥5000/1000/7000 tokens | ✓ |
| junction-conversational | junction | `~/.tpipe/debug/trace/Library/junction-live-bedrock/discussion-conversational/junction.html` | 13 events | ✓ |
| junction-vote-plan-output-exit | junction | `~/.tpipe/debug/trace/Library/junction-live-bedrock/workflow-vote_plan_output_exit/junction.html` | 18 events | ✓ |
| distribution-grid-strict-execution | distribution_grid | `~/.tpipe/debug/trace/Library/distribution-grid-live-bedrock/manual-core-qwen-two-node/strict-execution/sender-grid.html` | 18 events | ✓ |
| distribution-grid-policy-visible | distribution_grid | `~/.tpipe/debug/trace/Library/distribution-grid-live-bedrock/manual-core-qwen-two-node/trace-policy-visible/sender-grid.html` | 18 events | ✓ |
| agent-judge-interrupt | standard_pipeline | `~/.tpipe/debug/trace/tpipe-config-interrupt-live/agent-judge.html` | tokens ≥100/50 | ✓ |
| manifold-nested-reasoning-bug | manifold | `~/.tpipe/debug/trace/Library/nested-reasoning-bug/llama4-maverick/manifold-execution.html` | 45 events, includes MANIFOLD_FAILURE + P2P_REQUEST_FAILURE | ✓ |
| manifold-nested-reasoning-bug-json | json | `~/.tpipe/debug/trace/Library/nested-reasoning-bug/llama4-maverick/manifold-execution.json` | 45 events, 4868 responseLength + 6540 resultTextLength | ✓ |
| reversal-agent-json | json | `~/.tpipe/autogenesis-trace/Round_1_Turn_2_Narjan_Goren/ReversalAgent/trace.json` | 54 events, 6 token fields + 2 length fields | ✓ |

Stress-test status (2026-07-24): all 61 autogenesis JSON traces + 24 HTML traces (pumpstation, junction, distribution_grid, manifold, standard_pipeline) pass event-count + token-count validation against independent ground-truth extraction. The 56-of-61 length-conflation bug and the Layout B 0-events bug (Junction/DistributionGrid/Manifold reports returning 0 events) were caught and fixed before this skill was finalized.

**Note on path freshness**: Pumpstation trace paths include a millisecond-precision runId (`ps-178493312`). Re-running the steering/interrupt tests will produce a new runId. Capture with `verify_extraction.py --add <name> <path>` and update the case.

## Companion files

- `references/html-format-reference.md` — exact byte-level reference for both HTML container formats, with annotated samples and the regexes that match each block.
- `references/json-format-reference.md` — `List[TraceEvent]` schema, MapAnySerializer behavior, token field taxonomy.
- `references/triage-recipes.md` — concrete recipes for "tests passed but tokens burned budget", "judge always says yes", "loop guard tripped" — each recipe shows the exact command + expected output.
- `references/autogenesis-coverage-pitfalls.md` — known gaps in autogenesis trace fields (inputText snapshots vs fullPrompt, contextMap key taxonomy).
- `references/autogenesis-inputtext-coverage-pitfalls.md` — full v1.8 / v1.9 / v2.0 / v2.1 history of the story-vs-game-data classifier (Format A/B/C/D + opaque heuristic + longest-capture rule + verified R1T0/R2T0 per-call output tables + the per-time-not-sum workflow correction).
- `references/html-layout-b-containers.md` — Junction/Manifold/DistributionGrid Layout B regex set (article/div `<header class="event-header">` events, not `<tr>` rows).
- `references/parser-bug-history.md` — the history of every parser bug the verification suite has caught (length-vs-token, Layout B, nested-envelope).
- `references/audio-injection-pattern.md` — the world-snapshot `audioTracks` injection pattern that inflated autogenesis per-turn input tokens ~2x in 2026-07-25. Detection recipe + grep + verification command.
- `references/autogenesis-round-level-capture.md` — how to find the geoplitics (and other once-per-round) producer pipes when the captured name doesn't match the functional name. Synthesizes producer = `Synthesis Stage (<PlayerName>)`, consumers = `Planning/Execution Stage` + `explicit cot` + `Play Detection Agent`. Load when the user asks for round-level or function-level token tallies.
- `references/trace-parse-playbook.md` — decision tree for which extractor to use when.
- `references/event-types.md` — full PumpStation event inventory by source branch.
- `references/pumpstation-interrupt-steering-events.md` — `PUMP_STATION_STEERING_INJECTED` / `PUMP_STATION_INTERRUPT_FIRED` / `PUMP_STATION_INTERRUPT_OVERFLOW_DROPPED` capture, the nested-envelope rendering bug, and the regex fix.
- `references/live-test-infrastructure.md` — env-var gates (`TPIPE_LIVE_LLM_TEST` vs `AllowTest`), credential sources, output paths for every live test that produces trace artifacts.
- `scripts/parse_html_trace.py` — the HTML parser (verified).
- `scripts/parse_json_trace.py` — the JSON parser (verified).
- `scripts/extract_pipeline.py` — directory-level aggregator (verified).
- `scripts/verify_extraction.py` — self-test harness with seven pinned cases.
- `scripts/stress-test-parsers.sh` — run `verify_extraction.py` against every JSON trace on disk.
- `scripts/find-live-tests.sh` — enumerate every TPipe live test class with its container type and env vars. Run before claiming "no live test exists for X".
- `scripts/find-live-tests.sh` — enumerate every live test that saves trace artifacts.
- `scripts/autogenesis_attribution.py` — per-pipe game-data-vs-story input token attribution for Autogenesis turn traces. Usage: `python3 scripts/autogenesis_attribution.py --dir /path/to/turn/`. Handles Format A/B/C/D + multi-JSON + opaque content-shape heuristic (99.2% R1T0 coverage).

## Why this skill exists (and what it's NOT for)

This skill is for **reading and understanding trace files** after they exist on disk. It is NOT for:
- Modifying the trace pipeline itself — that's `tpipe-trace-output-conventions` (the path-resolution + emission conventions).
- Configuring what gets captured — that's the producer side (`TraceConfig`, `PumpStationTracingDsl`).
- Generating traces — that's `TraceVisualizer.kt`.

If you're debugging "why did the test pass but the trace is missing", load `tpipe-trace-output-conventions` first. If you're parsing a trace you already have, use the scripts here.