#!/usr/bin/env python3
"""
Standard TPipe HTML agent trace parser.

Extracts API_CALL_START/SUCCESS/FAILURE and PIPE_FAILURE events from
standard TPipe HTML agent traces (the `agent-XX.html` files that ship
alongside `pumpstation-ps-XX.html` and other trace folders).

Output JSON shape:
    {
        "path": "...",
        "event_count": N,
        "events": [
            {
                "row_idx": int,
                "time_ms": int,
                "pipe": "judge|dispatch|report|...",
                "type": "API_CALL_SUCCESS|PIPE_FAILURE|...",
                "phase": "EXECUTION|...",
                "model": "MiniMax-M2.7|...",
                "input_tokens": "3517"|null,
                "output_tokens": "558"|null,
                "total_tokens": "4075"|null,
                "output_text": "..."|null,
                "reasoning": "..."|null,
                "error": "Failed to parse HTTP response: ..."|null,
                "garbage_suspected": bool
            },
            ...
        ]
    }

Usage:
    python3 parse_agent_trace.py --input /path/to/agent-judge.html --output /tmp/parsed.json
    python3 parse_agent_trace.py --input /path/to/agent-judge.html   # prints summary
"""
import argparse
import json
import re
import sys
from html import unescape


def parse_agent_trace(path):
    """Parse a standard TPipe HTML agent trace.

    The trace format is a <table> with one <tr id='trace-event-N'> per event.
    Each row contains flattened text including time delta, pipe name, event type,
    phase, status, and a metadata block (model, token counts, etc.).
    """
    with open(path) as f:
        html = f.read()

    # Use a non-greedy split that terminates at the next <tr or </tbody>.
    rows = re.findall(
        r"<tr[^>]+?id=['\"]trace-event-(\d+)['\"][^>]*>([\s\S]*?)(?=<tr|</tbody>)",
        html,
    )

    events = []
    for idx, body in rows:
        flat = re.sub(r"<[^>]+>", " ", body)
        flat = re.sub(r"\s+", " ", flat).strip()

        # First fields: +Nms, pipe, event type, phase, status emoji+word, then metadata block
        m = re.match(
            r"\+?(\d+)ms\s+(\S+)\s+([A-Z_]+)\s+([A-Z_]+)\s+[^\s]+\s+(.*)",
            flat, re.DOTALL,
        )
        if not m:
            continue
        time_ms, pipe, etype, phase, rest = m.groups()

        # Only keep the events we care about; the full trace has many more
        if "API_CALL" not in etype and "PIPE_FAILURE" not in etype and "EXCEPTION" not in etype:
            continue

        # Extract model
        model_m = re.search(r"\bmodel:\s*(\S+)", rest)
        model = model_m.group(1) if model_m else None

        # Extract token counts (they appear in the metadata block after the status)
        in_tok = re.search(r"\binputTokens:\s*([0-9,]+)", rest)
        out_tok = re.search(r"\boutputTokens:\s*([0-9,]+)", rest)
        tot_tok = re.search(r"\btotalTokens:\s*([0-9,]+)", rest)
        in_tok_v = in_tok.group(1).replace(",", "") if in_tok else None
        out_tok_v = out_tok.group(1).replace(",", "") if out_tok else None
        tot_tok_v = tot_tok.group(1).replace(",", "") if tot_tok else None

        # Extract error
        err_m = re.search(r"\b(?:Error|error):\s*([^\n]{1,300})", rest)
        error = err_m.group(1).strip() if err_m else None

        # Extract output content (between "Output Content" and the next "reasoningContent" or end)
        out_m = re.search(
            r"Output Content\s*(?:\([0-9,]+ chars\))?\s*(.*?)(?:reasoningContent|Input Content|$)",
            flat, re.DOTALL,
        )
        output_text = out_m.group(1).strip()[:1500] if out_m else None

        # Extract reasoning content (after "reasoningContent")
        rc_m = re.search(
            r"reasoningContent\s*(?:\([0-9,]+ chars\))?\s*(.*?)(?:Input Content|Output Content|$)",
            flat, re.DOTALL,
        )
        reasoning = rc_m.group(1).strip()[:1500] if rc_m else None

        # Detect the "Drawing from my background" garbage pattern
        garbage = bool(output_text and "Drawing from my background" in output_text)

        events.append({
            "row_idx": int(idx),
            "time_ms": int(time_ms),
            "pipe": pipe,
            "type": etype,
            "phase": phase,
            "model": model,
            "input_tokens": in_tok_v,
            "output_tokens": out_tok_v,
            "total_tokens": tot_tok_v,
            "output_text": output_text,
            "reasoning": reasoning,
            "error": error,
            "garbage_suspected": garbage,
        })

    return {"path": str(path), "events": events, "event_count": len(events)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="Path to a agent-XX.html file")
    ap.add_argument("--output", help="Write JSON output to this path")
    ap.add_argument("--quiet", action="store_true", help="Only emit JSON, no summary")
    args = ap.parse_args()

    parsed = parse_agent_trace(args.input)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(parsed, f, indent=2, default=str)
        if not args.quiet:
            print(f"Wrote {parsed['event_count']} events to {args.output}", file=sys.stderr)
    else:
        if args.quiet:
            json.dump(parsed, sys.stdout, indent=2, default=str)
            print()
        else:
            print(f"\n=== {parsed['path']} ({parsed['event_count']} events) ===")
            for e in parsed["events"]:
                extra = ""
                if e["model"]: extra += f" model={e['model']}"
                if e["input_tokens"]: extra += f" in={e['input_tokens']} out={e['output_tokens']}"
                if e["error"]: extra += f" ERR={e['error'][:80]}"
                if e["garbage_suspected"]: extra += " GARBAGE"
                print(f"  +{e['time_ms']}ms {e['pipe']:20s} {e['type']:20s}{extra}")
                if e["output_text"]:
                    print(f"    OUT[:200]: {e['output_text'][:200]!r}")


if __name__ == "__main__":
    main()