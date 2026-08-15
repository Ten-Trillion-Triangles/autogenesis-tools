#!/usr/bin/env python3
"""
PumpStation HTML trace parser.

Extracts events from PumpStation-format HTML traces into structured JSON.
Handles the quirks described in the SKILL.md "PumpStation HTML Trace Format"
section (single-quoted attrs, trailing-colon meta keys, packed detail fields,
JSON reason extraction from contentPreview).

Usage:
    python3 parse_pumpstation_html.py --input /path/to/pumpstation-ps-123.html --output /tmp/parsed.json
    python3 parse_pumpstation_html.py --input /path/to/pumpstation-ps-123.html          # prints summary
    cat /path/to/*.html | python3 parse_pumpstation_html.py --stdin --output /tmp/all.json

Output JSON shape:
    {
        "path": "...",
        "run_status": "completed|running|failed|suspended|null",
        "run_id": "abcdef12",
        "event_count": N,
        "events": [
            {
                "type": "PUMP_STATION_JUDGE_COMPLETED",
                "label": "Judge completed (turn 1)",
                "meta": {"isComplete": "false", "reasonText": "...extracted from contentPreview JSON..."},
                "text": "...event-text block content if present..."
            },
            ...
        ]
    }
"""
import argparse
import json
import re
import sys
from html import unescape


def extract_reason_from_preview(content_preview):
    """Extract the `reason` field from the JSON wrapped inside a contentPreview meta-value.

    contentPreview values look like:  text=```json\n{...}\n```
    or:                              text={"foo": "bar"}

    Returns the unescaped reason string, or None.
    """
    if not content_preview:
        return None
    text = content_preview
    if text.startswith("text="):
        text = text[5:]
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj.get("reason")
    except Exception:
        pass
    return None


def parse_pumpstation_html(path):
    """Parse a PumpStation HTML trace file into structured events.

    Each event includes its type, label, meta dict, and any event-text block.
    The meta dict always strips trailing colons on keys and unescapes HTML entities.
    If a meta entry is `contentPreview` and contains a JSON object with a `reason`
    field, the reason is surfaced as `meta.reasonText` for easy access.

    Special handling:
    - LoopGuardTripped `detail` field (which packs consecutive=N, limit=N) is left
      as a single string. Callers that need the numbers should split on commas.
      (See SKILL.md pitfall: "Loop-guard detail packed in single field".)
    - Event types with empty meta (notably PUMP_STATION_COMPLETED — see the
      PumpStation triage report's Bug 1) are surfaced as-is so callers can detect
      the funnel gap.
    """
    with open(path) as f:
        html = f.read()

    # Event block: <div class='ps-detail-label'>LABEL<span class='ps-detail-type'>(TYPE)</span></div>
    # followed by the meta block, ending at the next ps-detail-label or </body>.
    pattern = re.compile(
        r"<div class='ps-detail-label'>([^<]+)<span class='ps-detail-type'>\(([^)]+)\)</span></div>"
        r"(.*?)"
        r"(?=<div class='ps-detail-label'>|</body>)",
        re.DOTALL,
    )

    events = []
    for m in pattern.finditer(html):
        label = m.group(1).strip()
        evt = m.group(2).strip()
        body = m.group(3)

        meta = {}
        for k, v in re.findall(
            r"<span class='ps-meta-key'>([^<]+)</span><span class='ps-meta-val'>([^<]+)</span>",
            body,
        ):
            meta[k.rstrip(":").strip()] = unescape(v.strip())

        # If contentPreview wraps a JSON verdict with a reason, surface it as meta.reasonText
        if "contentPreview" in meta:
            reason = extract_reason_from_preview(meta["contentPreview"])
            if reason:
                meta["reasonText"] = unescape(reason)

        # Extract <pre class='ps-event-text'> blocks (truncated to 5000 chars)
        text_matches = re.findall(
            r"<pre class='ps-event-text'>(.*?)</pre>", body, re.DOTALL
        )
        text = "\n---\n".join(text_matches) if text_matches else None

        events.append({
            "type": evt,
            "label": unescape(label),
            "meta": meta,
            "text": unescape(text[:5000]) if text else None,
        })

    # Run-level status from the header badge
    status_match = re.search(r"class=['\"]ps-status ps-status-(\w+)['\"]", html)
    run_status = status_match.group(1) if status_match else None

    # runId from the header
    runid_match = re.search(r"runId[:\s<>/a-z]+([0-9a-f]{8,})", html)
    run_id = runid_match.group(1) if runid_match else None

    return {
        "path": str(path),
        "run_status": run_status,
        "run_id": run_id,
        "events": events,
        "event_count": len(events),
    }


def summarize(parsed):
    """Print a one-line-per-event summary to stdout."""
    print(f"=== {parsed['path']} ===")
    print(f"  status={parsed['run_status']} events={parsed['event_count']}")
    for e in parsed["events"]:
        meta = e["meta"]
        interesting_keys = (
            "isComplete", "shouldTerminate", "selectedPathName", "pathName",
            "riskLevel", "approved", "warningCode", "guard", "trigger",
            "exitReason", "reason", "result", "memoryMode",
        )
        interesting = {k: meta[k] for k in interesting_keys if k in meta}
        if "reasonText" in meta:
            interesting["reasonText"] = meta["reasonText"][:120]
        if interesting:
            print(f"    {e['type']:50s} {interesting}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", help="Path to a pumpstation-ps-*.html file")
    ap.add_argument("--stdin", action="store_true", help="Read HTML from stdin")
    ap.add_argument("--output", help="Write JSON output to this path (default: stdout)")
    ap.add_argument("--quiet", action="store_true", help="Suppress summary, only emit JSON")
    args = ap.parse_args()

    if args.stdin:
        html = sys.stdin.read()
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            tmp = f.name
        parsed = parse_pumpstation_html(tmp)
        parsed["path"] = "<stdin>"
    elif args.input:
        parsed = parse_pumpstation_html(args.input)
    else:
        ap.error("either --input or --stdin is required")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(parsed, f, indent=2, default=str)
        if not args.quiet:
            print(f"Wrote {parsed['event_count']} events to {args.output}", file=sys.stderr)
    else:
        if not args.quiet:
            summarize(parsed)
        else:
            json.dump(parsed, sys.stdout, indent=2, default=str)
            print()


if __name__ == "__main__":
    main()