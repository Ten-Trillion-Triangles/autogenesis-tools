#!/usr/bin/env python3
"""
find_lorebanks.py — Discover autogenesis lorebank narrative-trace files at
~/.tpipe/TPipe-Default/memory/lorebook/.

Usage:
    python3 scripts/find_lorebanks.py                       # list everything
    python3 scripts/find_lorebanks.py "Lord Maple Tree"     # substring match on persona name
    python3 scripts/find_lorebanks.py --worlds              # only world banks (no -<persona> suffix)
    python3 scripts/find_lorebanks.py --personas "Wilfred"  # only persona banks
    python3 scripts/find_lorebanks.py --preview 200         # chars of preview text (default 160)
    python3 scripts/find_lorebanks.py --json                # machine-readable JSON output

Output (default human-readable): one row per file:
    <persona-or-world>  <size>  <session-id>  <filename>   <latest-entry preview>

Use this to jump from "what does Lord Maple Tree actually say" to the file that
proves it. For full content, read the file directly with read_file (offset/limit
for the long world banks).
"""

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_DIR = os.path.expanduser("~/.tpipe/TPipe-Default/memory/lorebook")

# Filename patterns
CHAT_BANK_RE = re.compile(r"^chat-kvision-ws-client-([0-9]+)-(.+)\.bank$")
WORLD_BANK_RE = re.compile(r"^kvision-ws-client-([0-9]+)\.bank$")


def classify(path: str) -> tuple[str, str]:
    """Return (kind, key) where kind is 'chat' or 'world' and key is the session id."""
    fname = os.path.basename(path)
    m = CHAT_BANK_RE.match(fname)
    if m:
        return ("chat", m.group(1))
    m = WORLD_BANK_RE.match(fname)
    if m:
        return ("world", m.group(1))
    return ("other", fname)


def latest_text(path: str) -> str:
    """Read the most recent assistant entry's text from a lorebank. Falls back to empty."""
    try:
        with open(path) as f:
            data = json.load(f)
        history = data.get("converseHistory", {}).get("history", [])
        if not history:
            return ""
        # Walk backwards, prefer assistant entries
        for entry in reversed(history):
            if entry.get("role") == "assistant":
                txt = entry.get("content", {}).get("text", "")
                if txt:
                    return txt
        # If no assistant found, take the last entry
        return history[-1].get("content", {}).get("text", "")
    except Exception as e:
        return f"[read error: {e}]"


def persona_from_path(path: str) -> str:
    m = CHAT_BANK_RE.match(os.path.basename(path))
    return m.group(2) if m else "—world—"


def session_id_from_path(path: str) -> str:
    m = CHAT_BANK_RE.match(os.path.basename(path))
    if m:
        return m.group(1)
    m = WORLD_BANK_RE.match(os.path.basename(path))
    return m.group(1) if m else "?"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("persona", nargs="?", default=None,
                   help="Substring match on persona name (chat banks only). Case-insensitive.")
    p.add_argument("--worlds", action="store_true",
                   help="Only list world banks (kvision-ws-client-<id>.bank, no -<persona> suffix).")
    p.add_argument("--personas", default=None, metavar="SUBSTRING",
                   help="Only list persona banks (chat-kvision-ws-client-<id>-<persona>.bank). "
                        "Optional substring match on the persona name.")
    p.add_argument("--dir", default=DEFAULT_DIR,
                   help=f"Override the lorebank directory (default: {DEFAULT_DIR}).")
    p.add_argument("--preview", type=int, default=160, metavar="CHARS",
                   help="Number of characters of preview text per row (default 160, 0 to suppress).")
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON instead of human-readable rows.")
    args = p.parse_args()

    if not os.path.isdir(args.dir):
        print(f"Error: lorebank directory does not exist: {args.dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(glob.glob(os.path.join(args.dir, "*.bank")))

    # Apply filters
    rows = []
    for f in files:
        kind, sid = classify(f)
        if kind == "other":
            continue
        if args.worlds and kind != "world":
            continue
        if args.personas is not None and kind != "chat":
            continue
        if args.worlds is False and args.personas is None and args.persona and kind == "world":
            # Default persona filter also excludes world banks unless --worlds is set
            continue
        if args.persona and kind == "chat":
            if args.persona.lower() not in persona_from_path(f).lower():
                continue
        if args.personas and kind == "chat":
            if args.personas.lower() not in persona_from_path(f).lower():
                continue
        rows.append(f)

    if args.json:
        out = []
        for f in rows:
            kind, sid = classify(f)
            entry = {
                "path": f,
                "filename": os.path.basename(f),
                "kind": kind,
                "session_id": sid,
                "persona": persona_from_path(f) if kind == "chat" else None,
                "size_bytes": os.path.getsize(f),
            }
            if args.preview != 0:
                preview = latest_text(f).replace("\n", " ⏎ ")
                if len(preview) > args.preview:
                    preview = preview[: args.preview - 3] + "..."
                entry["latest_text_preview"] = preview
            out.append(entry)
        print(json.dumps(out, indent=2))
        return

    # Human-readable output
    if not rows:
        print(f"No lorebank files matched. Directory: {args.dir}")
        if args.persona:
            print(f"  Filter: persona contains '{args.persona}'")
        return

    print(f"# {len(rows)} lorebank file(s) in {args.dir}")
    if args.persona:
        print(f"# Filter: persona contains '{args.persona}'")
    elif args.worlds:
        print(f"# Filter: world banks only")
    elif args.personas is not None:
        print(f"# Filter: persona banks only (substring: '{args.personas}')")
    print()

    # Compute column widths
    fn_width = max(len(os.path.basename(f)) for f in rows)
    fn_width = min(max(fn_width, 30), 60)
    persona_width = min(max((len(persona_from_path(f)) for f in rows), default=15), 30)

    for f in rows:
        kind, sid = classify(f)
        size = os.path.getsize(f)
        persona = persona_from_path(f) if kind == "chat" else "—world—"
        fname = os.path.basename(f)
        size_str = f"{size:>7,}b"
        if args.preview > 0:
            preview = latest_text(f).replace("\n", " ⏎ ")
            if len(preview) > args.preview:
                preview = preview[: args.preview - 3] + "..."
        else:
            preview = ""
        print(f"  [{sid}]  {persona:<{persona_width}}  {size_str}  {fname}")
        if preview:
            print(f"    └─ {preview}")


if __name__ == "__main__":
    main()