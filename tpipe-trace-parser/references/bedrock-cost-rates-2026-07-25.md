---
title: Bedrock cost rates — for trace-derived cost/pricing artifacts
last_verified: 2026-07-25
verified_against: live Round 3 traces at /home/cage/.tpipe/debug/trace/
---

# Bedrock cost rates — what to apply when deriving cost from traces

## TL;DR — the canonical rate card (2026-07-25)

| Model | $ / M in | $ / M out | Flex $ / M in | Notes |
|-------|----------|-----------|--------------|-------|
| qwen3-coder-30b-a3b | $0.15 | $0.28 | $0.07 | workhorse, default + Flex JSON-only modes |
| qwen3-235b-a22b-2507 | $0.40 | $1.20 | n/a | being replaced by coder (charged at coder rate per operator) |
| palmyra-x5 (writer) | $0.60 | $1.50 | n/a | current writer — swap target is nova-lite |
| nova-lite | $0.06 | $0.24 | n/a | writer-swap candidate |
| nova-micro | $0.035 | $0.14 | n/a | cheapest option |
| llama-4-scout | $0.17 | $0.66 | n/a | 10M context |
| llama-4-maverick | $0.24 | $0.97 | n/a | 1M context |
| claude-haiku-4.5 | $0.80 | $4.00 | n/a | 200K context |
| claude-sonnet-4.6 | $3.00 | $15.00 | n/a | 200K context |
| claude-opus-4.7 | $15.00 | $75.00 | n/a | 200K context |

## The trap — three "coder rates" that have been confused

There are THREE different rates that have been used in pricing artifacts, all called qwen coder or coder rate:

1. Open-source Qwen 30B-A3B API rate: $0.08 / M in — the rate on Alibaba Cloud / OpenRouter / etc. for the open-source model. This is what the v3 PDF used.
2. Bedrock qwen3-coder-30b-a3b default rate: $0.15 / M in — the rate on AWS Bedrock serverless. This is the actual rate for traces captured from ~/.tpipe/debug/trace/.
3. Bedrock qwen3-coder-30b-a3b Flex JSON-only rate: $0.07 / M in — the rate when invoking via Bedrock Flex mode with JSON-only output schema. Applied to calls with small JSON output (< 5K output tokens).

Why this matters. At v4 actual human-turn cost ($0.1867 = 1,280,279 input tokens), the per-game cost at E[12 rounds] swings wildly depending on which rate you apply:

- v3 PDF (used $0.08): $2.28 / game — hallucinated, off by ~3x from reality
- v4 PDF (used $0.15 + $0.07 Flex mix): $5.21 / game — canonical, matches the clean Round 3 trace

Using the wrong rate produces a pricing artifact that looks plausible but is 3x under-costed. The break-even math then looks generous when it is actually catastrophic.

## When to apply which rate

Apply $0.07 Flex rate to coder calls where:
- Output is small (operator verified: < 5K output tokens)
- AND the call goes through Bedrock Flex mode (which is what most autogenesis-game coder calls use per the trace metadata)

Apply $0.15 default rate to coder calls where:
- Output is large (>= 5K output tokens), OR
- The call does not go through Flex mode

Apply $0.40 / 1.20 rate to qwen3-235b calls — BUT per the operator (2026-07-25), 235b is being replaced by 30b. The replacement is gradual. If you see 235b in trace metadata, the canonical interpretation is "this would have been charged at coder rate if the migration were complete." Do not use $0.40 in any new artifact unless you are specifically modeling the pre-migration cost.

Apply $0.60 / 1.50 rate to palmyra-x5 calls — these are the writer. At v4 cost, palmyra-x5 is 80% of NPC turn cost (because the NPC pipeline runs the writer heavily). Do not conflate with coder rates.

Apply $0.06 / 0.24 rate to nova-lite calls — only relevant if the palmyra-x5 -> nova-lite swap has shipped. At the time of writing (2026-07-25), the swap is a benchmark candidate, not shipped.

## Detection recipe — verify the rate before deriving cost

```bash
python3 << 'PY'
import json, glob
from pathlib import Path

base = "/home/cage/.tpipe/debug/trace"
models = set()
for fp in glob.glob(f"{base}/**/trace.json", recursive=True):
    for ev in json.load(open(fp)):
        m = ev.get("metadata", {}).get("model")
        if m:
            models.add(m)
for m in sorted(models):
    print(m)
PY
```

Then match each model to its rate from the table above, sum (input / 1_000_000 * input_rate) + (output / 1_000_000 * output_rate), and compare against the artifact headline cost. If off by more than 10%, the rate is wrong.

## How Flex detection works in the trace

The trace metadata field `apiType` or `useConverseApi` indicates whether the call went through Flex mode. If `apiType == "Flex"` or `useConverseApi == true`, apply the $0.07 rate. Otherwise apply $0.15.

If the trace does not disambiguate, assume default ($0.15). The 5K output-token threshold for Flex is a heuristic from the operator; adjust if the trace metadata provides a more specific signal.

## Why this matters for pricing artifacts

If you are building any of these:
- Margin model PDF
- Per-tier COGS projection
- MAU x profit threshold table
- Risk-adjusted margin ladder
- Token allowance truth table

The pricing model depends on which rate you apply to which call. The v3 -> v4 PDF rebuild showed that the same traces produced $2.28/game (wrong) vs $5.21/game (right) — a 2.3x swing — purely from the rate card.

The trap: the rate is in a different file from the trace data, and a future session that picks up the trace data without the rate card will default to the open-source rate ($0.08), which produces the v3 hallucination.

## Cross-reference

- references/audio-injection-pattern.md — the bug that contaminated ~/.tpipe/autogenesis-trace/. Only ~/.tpipe/debug/trace/ is trustworthy for cost derivation.
- The token taxonomy table in SKILL.md — the scope (per-call vs cumulative) is one axis of confusion; the rate card is the other. Both must be pinned together.

## Verification command — run before shipping any cost artifact

```bash
python3 << 'PY'
import json, glob

RATES = {
    "qwen.qwen3-coder-30b-a3b": (0.15, 0.28),
    "qwen.qwen3-235b-a22b": (0.40, 1.20),
    "us.writer.palmyra-x5": (0.60, 1.50),
}

total_cost = 0.0
total_in = 0
total_out = 0
for fp in glob.glob("/home/cage/.tpipe/debug/trace/**/trace.json", recursive=True):
    for ev in json.load(open(fp)):
        meta = ev.get("metadata", {})
        m = meta.get("model", "")
        inp = int(meta.get("inputTokens") or 0)
        out = int(meta.get("outputTokens") or 0)
        rate = RATES.get(m.split("/")[-1], (0.15, 0.28))
        if "coder-30b" in m and meta.get("apiType") == "Flex":
            rate = (0.07, 0.28)
        if "235b" in m:
            rate = (0.15, 0.28)
        cost = inp / 1_000_000 * rate[0] + out / 1_000_000 * rate[1]
        total_cost += cost
        total_in += inp
        total_out += out
print(f"Total cost: ${total_cost:.4f}")
print(f"Total input: {total_in:,}")
print(f"Total output: {total_out:,}")
PY
```

Expected output for the Round 3 clean trace at v4 rates: $0.9978 total cost, 7,181,332 input, 714,568 output. If your artifact claims a different total, the rate or the bucket is wrong.
