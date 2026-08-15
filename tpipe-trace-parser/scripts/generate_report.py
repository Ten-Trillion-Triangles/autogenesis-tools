#!/usr/bin/env python3
"""
TPipe Trace Report Generator

Generates human-readable reports from parsed trace events.
Handles events from any parser (JSON, HTML, markdown).

Usage:
    python3 generate_report.py --input <parsed.json> --output <report.txt>
"""

import argparse
import json
import sys
from collections import defaultdict
from typing import List, Dict, Any


def load_events(input_path: str) -> List[Dict[str, Any]]:
    """Load parsed events from JSON file."""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Malformed JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    else:
        print(f"ERROR: Unexpected JSON root type: {type(data).__name__}", file=sys.stderr)
        sys.exit(1)


def is_success_event(event: Dict[str, Any]) -> bool:
    status = event.get('status', '').lower()
    event_type = event.get('event', event.get('eventType', ''))
    return 'success' in status or '_SUCCESS' in event_type


def is_failure_event(event: Dict[str, Any]) -> bool:
    status = event.get('status', '').lower()
    event_type = event.get('event', event.get('eventType', ''))
    return 'failure' in status or 'fail' in status or '_FAILURE' in event_type


def format_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}m"


def format_time_delta(ms: int) -> str:
    return f"+{ms}ms"


def generate_summary(events: List[Dict[str, Any]]) -> str:
    total = len(events)
    if total == 0:
        return "## Summary\n\nNo events recorded.\n"

    success_count = sum(1 for e in events if is_success_event(e))
    failure_count = sum(1 for e in events if is_failure_event(e))
    info_count = total - success_count - failure_count

    event_types = defaultdict(int)
    for e in events:
        event_type = e.get('event', e.get('eventType', 'UNKNOWN'))
        event_types[event_type] += 1

    pipes = defaultdict(int)
    for e in events:
        pipe = e.get('pipe', e.get('pipeName', 'Unknown'))
        pipes[pipe] += 1

    times = [e.get('timestamp', 0) for e in events if e.get('timestamp', 0) > 0]
    if len(times) >= 2:
        exec_time_ms = max(times) - min(times)
        exec_time_str = format_duration(exec_time_ms)
    else:
        time_deltas = [e.get('timeDeltaMs', 0) for e in events if e.get('timeDeltaMs', 0) > 0]
        exec_time_str = format_duration(max(time_deltas)) if time_deltas else "unknown"

    lines = [
        "## Summary", "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Events | {total} |",
        f"| Success | {success_count} |",
        f"| Failure | {failure_count} |",
        f"| Info | {info_count} |",
        f"| Execution Time | {exec_time_str} |",
        f"| Unique Pipes | {len(pipes)} |",
        f"| Unique Event Types | {len(event_types)} |", "",
        "### Pipes",
    ]

    for pipe, count in sorted(pipes.items(), key=lambda x: -x[1])[:5]:
        lines.append(f"- {pipe}: {count} events")
    if len(pipes) > 5:
        lines.append(f"- ... and {len(pipes) - 5} more")

    lines.extend(["", "### Top Event Types"])
    for event_type, count in sorted(event_types.items(), key=lambda x: -x[1])[:5]:
        lines.append(f"- {event_type}: {count}")

    return '\n'.join(lines)


def generate_timeline(events: List[Dict[str, Any]], max_events: int = 100) -> str:
    if not events:
        return "## Timeline\n\nNo events recorded.\n"

    lines = [
        "## Timeline", "",
        "| # | Time | Pipe | Event | Phase | Status |",
        "|---|------|------|-------|-------|--------|",
    ]

    sorted_events = sorted(events, key=lambda e: (e.get('timestamp', 0), e.get('timeDeltaMs', 0)))
    display_events = sorted_events[:max_events]

    for i, e in enumerate(display_events, 1):
        time_str = e.get('time', format_time_delta(e.get('timeDeltaMs', i * 100)))
        pipe = e.get('pipe', e.get('pipeName', 'Unknown'))[:20]
        event = e.get('event', e.get('eventType', 'UNKNOWN'))[:30]
        phase = e.get('phase', '-')
        status = e.get('status', '-')
        lines.append(f"| {i} | {time_str} | {pipe} | {event} | {phase} | {status} |")

    if len(sorted_events) > max_events:
        lines.append(f"| ... | ({len(sorted_events) - max_events} more events) |")

    return '\n'.join(lines)


def generate_errors(events: List[Dict[str, Any]]) -> str:
    failures = [e for e in events if is_failure_event(e)]

    if not failures:
        return "## Errors\n\nNo failures detected.\n"

    lines = [
        "## Errors", "",
        f"Found {len(failures)} failure(s):", "",
    ]

    for i, e in enumerate(failures[:20], 1):
        time_str = e.get('time', f"+{e.get('timeDeltaMs', 0)}ms")
        pipe = e.get('pipe', e.get('pipeName', 'Unknown'))
        event = e.get('event', e.get('eventType', 'UNKNOWN'))
        phase = e.get('phase', '-')
        lines.append(f"### {i}. {event} at {time_str}")
        lines.append(f"- Pipe: {pipe}")
        lines.append(f"- Phase: {phase}")
        metadata = e.get('metadata', {})
        if isinstance(metadata, dict):
            for key, value in list(metadata.items())[:5]:
                if key and value:
                    lines.append(f"- {key}: {str(value)[:50]}")
        lines.append("")

    if len(failures) > 20:
        lines.append(f"... and {len(failures) - 20} more failures")

    return '\n'.join(lines)


def generate_performance_metrics(events: List[Dict[str, Any]]) -> str:
    if not events:
        return "## Performance Metrics\n\nNo events recorded.\n"

    lines = ["## Performance Metrics", ""]

    phase_events = defaultdict(list)
    for e in events:
        phase = e.get('phase', 'UNKNOWN')
        time_delta = e.get('timeDeltaMs', 0)
        if time_delta > 0:
            phase_events[phase].append(time_delta)

    if phase_events:
        lines.append("### Phase Durations")
        lines.extend(["", "| Phase | Events | Total Time | Avg Time |", "|-------|--------|------------|----------|"])
        for phase, times in sorted(phase_events.items()):
            total = sum(times)
            avg = total // len(times) if times else 0
            lines.append(f"| {phase} | {len(times)} | {total}ms | {avg}ms |")
        lines.append("")

    api_events = [e for e in events if 'API' in e.get('event', e.get('eventType', ''))]
    if api_events:
        lines.append("### API Call Metrics")
        lines.extend(["", f"Total API calls: {len(api_events)}"])
        api_by_type = defaultdict(int)
        for e in api_events:
            api_by_type[e.get('event', e.get('eventType', 'UNKNOWN'))] += 1
        for event_type, count in sorted(api_by_type.items()):
            lines.append(f"- {event_type}: {count}")
        lines.append("")

    metadata_keys = set()
    for e in events:
        meta = e.get('metadata', {})
        if isinstance(meta, dict):
            metadata_keys.update(meta.keys())

    if metadata_keys:
        lines.append("### Metadata Keys Found")
        lines.append("")
        metadata_keys_list = sorted(metadata_keys)[:10]
        for key in metadata_keys_list:
            lines.append(f"- {key}")
        if len(metadata_keys) > 10:
            lines.append(f"- ... and {len(metadata_keys) - 10} more")
        lines.append("")

    return '\n'.join(lines)


def generate_report(input_path: str, output_path: str, max_timeline_events: int = 100) -> None:
    events = load_events(input_path)
    sections = [
        "# TPipe Trace Report", "",
        f"Generated from {len(events)} events", "",
        generate_summary(events), "",
        generate_timeline(events, max_timeline_events), "",
        generate_errors(events), "",
        generate_performance_metrics(events),
    ]
    report = '\n'.join(sections)

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
    except PermissionError:
        print(f"ERROR: Permission denied writing: {output_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Report: {len(events)} events -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate TPipe trace reports.')
    parser.add_argument('--input', '-i', required=True, help='Input parsed events JSON file path')
    parser.add_argument('--output', '-o', required=True, help='Output report text file path')
    parser.add_argument('--max-timeline', '-m', type=int, default=100, help='Max timeline events (default: 100)')
    args = parser.parse_args()
    generate_report(args.input, args.output, args.max_timeline)


if __name__ == '__main__':
    main()