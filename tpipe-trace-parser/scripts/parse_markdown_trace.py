#!/usr/bin/env python3
"""
TPipe Markdown Trace Parser

Parses TPipe MARKDOWN trace files and extracts structured event data
from markdown table structures.

Usage:
    python3 parse_markdown_trace.py --input <trace.md> --output <parsed.json>
"""

import argparse
import json
import re
import sys
from typing import List, Dict, Any, Optional


def parse_markdown_table(markdown_text: str) -> List[List[str]]:
    """Parse markdown table into list of rows."""
    lines = markdown_text.split('\n')
    rows = []
    in_table = False

    for line in lines:
        line = line.strip()
        if '|' in line and not line.startswith('```'):
            cells = [cell.strip() for cell in line.split('|')]
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]
            if cells and all(re.match(r'^[-:]+$', cell.replace(':', '').replace('-', '')) for cell in cells if cell):
                in_table = True
                continue
            if cells and in_table:
                rows.append(cells)

    return rows


def extract_events_from_markdown(markdown_content: str) -> List[Dict[str, Any]]:
    """Extract trace events from markdown content."""
    events = []
    table_sections = find_table_sections(markdown_content)

    for section in table_sections:
        rows = parse_markdown_table(section)
        if len(rows) < 2:
            continue

        header_row = rows[0]
        is_header = any(keyword in str(header_row).lower() for keyword in ['time', 'pipe', 'event', 'phase'])

        data_rows = rows[1:] if is_header else rows
        for row in data_rows:
            event = parse_row_to_event(row)
            if event:
                events.append(event)

    events.extend(extract_event_lists(markdown_content))
    return events


def find_table_sections(markdown_content: str) -> List[str]:
    """Find all table sections in markdown content."""
    lines = markdown_content.split('\n')
    sections = []
    current_section = []
    in_code_block = False

    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if '|' in line:
            current_section.append(line)
        else:
            if current_section:
                sections.append('\n'.join(current_section))
                current_section = []

    if current_section:
        sections.append('\n'.join(current_section))

    return sections


def parse_row_to_event(row: List[str]) -> Optional[Dict[str, Any]]:
    if len(row) < 4:
        return None

    try:
        return {
            'time': row[0] if len(row) > 0 else '',
            'pipe': row[1] if len(row) > 1 else '',
            'event': row[2] if len(row) > 2 else '',
            'phase': row[3] if len(row) > 3 else '',
            'status': row[4] if len(row) > 4 else '',
            'metadata': parse_metadata_string(row[5] if len(row) > 5 else ''),
        }
    except (IndexError, ValueError):
        return None


def parse_metadata_string(metadata_str: str) -> Dict[str, Any]:
    metadata = {}
    if not metadata_str or not metadata_str.strip():
        return metadata

    parts = re.split(r'[,\n]', metadata_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.match(r'^[\*]?([^:\*]+)[\*]?:\s*(.+)$', part)
        if match:
            key = match.group(1).strip()
            value = re.sub(r'[\*_]+', '', match.group(2).strip())
            if key:
                metadata[key] = value

    return metadata


def extract_event_lists(markdown_content: str) -> List[Dict[str, Any]]:
    """Extract events from non-table format (event lists)."""
    events = []
    current_event = {}

    sections = re.split(r'^##?\s+', markdown_content, flags=re.MULTILINE)
    for section in sections:
        lines = section.split('\n')
        if not lines:
            continue

        for line in lines:
            line = line.strip()
            match = re.match(r'^-\s+(\w+)\s*:\s*(.+)$', line)
            if match:
                key = match.group(1).lower()
                value = match.group(2).strip()
                if key in ['time', 'pipe', 'event', 'phase', 'status']:
                    current_event[key] = value
            elif not line and current_event:
                if 'event' in current_event:
                    events.append(current_event)
                current_event = {}

        if current_event and 'event' in current_event:
            events.append(current_event)
            current_event = {}

    return events


def main():
    parser = argparse.ArgumentParser(description='Parse TPipe markdown trace files.')
    parser.add_argument('--input', '-i', required=True, help='Input markdown trace file path')
    parser.add_argument('--output', '-o', required=True, help='Output parsed events JSON file path')
    args = parser.parse_args()

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"ERROR: Permission denied reading: {args.input}", file=sys.stderr)
        sys.exit(1)

    events = extract_events_from_markdown(markdown_content)

    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
    except PermissionError:
        print(f"ERROR: Permission denied writing: {args.output}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracted {len(events)} events -> {args.output}")


if __name__ == '__main__':
    main()