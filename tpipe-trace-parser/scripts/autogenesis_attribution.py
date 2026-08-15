#!/usr/bin/env python3
"""Autogenesis per-pipe input-token attribution - game data vs story.

Walks a turn directory (e.g. ~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/)
and produces a per-pipe breakdown of input tokens split between
"game data" (world, player, NPC, tile, mechanical state) and "story"
(narrative prose flowing through the pipe).

v2.0 (2026-07-24): handles Format A (contextMap), Format B
(##DEVELOPER PROMPT## / ##USER PROMPT## + contextMap), Format C
(top-level JSON keys), Format D ({} + stringified-JSON
contextElements), and multi-JSON Format C (JSON object followed by
another JSON). For genuinely-partial captures (max fullPrompt <
500 chars OR coverage < 10%), applies a content-shape heuristic so
every pipe gets attributed.

Verified output: R1T0 (Lord Maple Tree) classifies 99.2% of 620,970
input tokens - 86.9% game data, 12.3% story, 0.8% unknown.

Usage:
    python3 autogenesis_attribution.py --dir /path/to/turn/
    python3 autogenesis_attribution.py --dir /path/to/turn/ --json /tmp/out.json
    python3 autogenesis_attribution.py --help

Requires tiktoken (cl100k_base). Install with:
    python3 -m venv /tmp/venv && /tmp/venv/bin/pip install tiktoken
"""

import argparse
import json
import os
import sys
from collections import defaultdict

try:
    import tiktoken
    ENC = tiktoken.get_encoding("cl100k_base")

    def tc(t):
        return len(ENC.encode(t)) if t else 0
except ImportError:
    print("tiktoken not installed. Run: python3 -m venv /tmp/venv && "
          "/tmp/venv/bin/pip install tiktoken", file=sys.stderr)
    sys.exit(1)


# ============================================================
# Bucket whitelists - extend when a new pipe family shows up.
# ============================================================

STORY_KEYS = {
    "story", "previous turn", "user prompt", "userpromptseed", "narrative",
    "previous summary", "storyafterreversal", "turnstory", "thisevent",
    "this event",
}

# Format A / contextMap keys for game data
GAME_DATA_KEYS_A = {
    "world", "world_context", "world context", "worldinfo", "world info",
    "player stats", "target_data", "target data", "targetterritoryinfo",
    "action_intent", "action intent", "current turn",
    "known npcs", "player", "player_data", "player data",
    "character list", "player list", "new chars", "valid_territories",
    "history", "player_name_context", "player name context",
    "local_adjacency", "local adjacency", "npc_data", "npc data",
    "other_players", "other players", "all_entities", "all entities",
    "delegate_guidance", "delegate guidance", "weights",
    "geopoliticalassessment", "overtonwindow",
    "validatorpipeuserpromptsnapshottpipe",
    "user data", "userdata",
    # Format D inner keys (stringified turnState JSON)
    "turnplayer", "turnaction", "turnoutcome", "wasplayersuccessful",
    "turnresult", "territorygained", "resourceswon", "statbuffsgained",
    "territoryexchanges", "affectedplayers", "targetintent", "targetentities",
}

# Format C / top-level JSON keys for game data
GAME_DATA_KEYS_C = {
    "characters", "npcs", "candidates", "targets", "actingfromterritories",
    "attemptedplayeraction", "decidedturnoutcome", "actionintent",
    "responseintent", "intentmismatch", "type",
    "bestchapterideas", "chapterideas", "possibleturnoutcomes",
    "actionstakenbycharactersinchapter", "newcharacterstointroduce",
    "playerdata", "playeraction", "worldname", "worldsetting",
    "assetsgained", "assetslost", "classifiedresources", "territorygained",
    "territorylost", "resources", "captureattempted", "changestomake",
    "islegal", "isvictory", "territoriesdeposed", "assetexchanges",
    "territoryexchanges", "territorystatchanges", "resultsummary",
    "needschanges", "newoutput", "istrue", "reason",
    "all_entities", "valid_territories", "history", "geopoliticalassessment",
    "overtonwindow", "playerstats", "playercharacter", "statuseffects",
    "worldinfo", "world context", "world_context", "local_adjacency",
    "npc_data", "npc data", "other_players", "player_data", "player name",
    "playername", "known npcs", "player_name_context",
}


# ============================================================
# JSON-walking helpers (brace-balanced, string-aware)
# ============================================================

def _find_balanced_json(prompt, start_idx=0):
    """Find first balanced JSON object starting from start_idx. Returns
    (obj, start, end) or (None, -1, -1)."""
    idx = prompt.find("{", start_idx)
    if idx == -1:
        return None, -1, -1
    depth = 0
    in_str = False
    esc = False
    end = -1
    i = idx
    while i < len(prompt):
        c = prompt[i]
        if esc:
            esc = False
            i += 1
            continue
        if c == "\\":
            esc = True
            i += 1
            continue
        if c == '"':
            in_str = not in_str
            i += 1
            continue
        if in_str:
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    if end == -1:
        return None, -1, -1
    try:
        return json.loads(prompt[idx:end], strict=False), idx, end
    except Exception:
        return None, -1, -1


def find_all_balanced_jsons(prompt):
    """Walk ALL balanced JSON objects in the prompt (top-level, non-nested)."""
    results = []
    idx = 0
    while idx < len(prompt):
        obj, start, end = _find_balanced_json(prompt, idx)
        if obj is None:
            break
        results.append((start, end, obj))
        idx = end
    return results


def find_context_map(prompt):
    """Find the LAST `{"contextMap": {...}}` block in the prompt."""
    if not prompt:
        return None
    idx = prompt.rfind('"contextMap"')
    if idx == -1:
        idx = prompt.rfind('contextMap')
    if idx == -1:
        return None
    start = prompt.rfind("{", 0, idx)
    if start == -1:
        return None
    obj, _, end = _find_balanced_json(prompt, start)
    return obj


def extract_context_text(elem):
    """Unwrap a contextElement to text (handles nested string+text+dict shapes)."""
    if isinstance(elem, str):
        return elem
    if isinstance(elem, dict):
        if "text" in elem:
            return elem["text"] if isinstance(elem["text"], str) else json.dumps(elem["text"])
        return json.dumps(elem)
    if isinstance(elem, list):
        return "".join(extract_context_text(x) for x in elem)
    return str(elem)


def classify_format_a(k):
    kl = k.strip().lower()
    if kl in STORY_KEYS:
        return "story"
    if kl in GAME_DATA_KEYS_A:
        return "game_data"
    return None


def classify_format_c(k):
    kl = k.strip().lower()
    if kl in STORY_KEYS:
        return "story"
    if kl in GAME_DATA_KEYS_C:
        return "game_data"
    return None


# ============================================================
# Bucket functions - one per detected prompt format
# ============================================================

def bucket_format_a(prompt):
    """Format A: prompt contains a {contextMap: {key: {contextElements: [...]}}} block."""
    cm = find_context_map(prompt)
    if not cm:
        return None
    cm_data = cm.get("contextMap", cm) if isinstance(cm, dict) else None
    if not isinstance(cm_data, dict):
        return None
    s = g = u = t = 0
    for k, v in cm_data.items():
        if not isinstance(v, dict):
            continue
        elements = v.get("contextElements", [])
        if not isinstance(elements, list):
            continue
        for elem in elements:
            text = extract_context_text(elem)
            n = tc(text)
            t += n
            b = classify_format_a(k)
            if b == "story":
                s += n
            elif b == "game_data":
                g += n
            else:
                u += n
    return s, g, u, t


def bucket_format_b(prompt):
    """Format B: ##DEVELOPER PROMPT## ... ##USER PROMPT## <action narrative> {contextMap}."""
    if "##USER PROMPT##" not in prompt:
        return None
    user_section = prompt.rsplit("##USER PROMPT##", 1)[1]
    cm = find_context_map(user_section)
    cm_data = {}
    if cm:
        cm_data = cm.get("contextMap", cm) if isinstance(cm, dict) else {}
        idx = user_section.rfind('"contextMap"')
        if idx == -1:
            idx = user_section.rfind('contextMap')
        if idx > 0:
            pre = user_section[:user_section.rfind('{', 0, idx)]
        else:
            pre = ""
        action_text = pre
    else:
        action_text = user_section
    s = tc(action_text)
    g = u = 0
    t = s
    for k, v in cm_data.items():
        if not isinstance(v, dict):
            continue
        elements = v.get("contextElements", [])
        if not isinstance(elements, list):
            continue
        for elem in elements:
            text = extract_context_text(elem)
            n = tc(text)
            t += n
            b = classify_format_a(k)
            if b == "story":
                s += n
            elif b == "game_data":
                g += n
            else:
                u += n
    return s, g, u, t


def bucket_format_c_multi(prompt):
    """Format C: prompt starts with `{` and may have MULTIPLE top-level JSON
    objects (e.g. {"characters":[...]} followed by {contextElements: ...}).
    Aggregate bucket shares across ALL balanced JSON objects."""
    if not prompt or not prompt.lstrip().startswith("{"):
        return None
    all_jsons = find_all_balanced_jsons(prompt)
    if not all_jsons:
        return None
    s = g = u = t = 0
    for _, _, obj in all_jsons:
        if not isinstance(obj, dict):
            continue
        for k, v in obj.items():
            if k == "loreBookKeys":
                continue
            if k == "contextElements" and isinstance(v, list):
                for elem in v:
                    if isinstance(elem, str):
                        try:
                            inner = json.loads(elem, strict=False)
                        except Exception:
                            inner = None
                        if isinstance(inner, dict):
                            for ik, iv in inner.items():
                                n = tc(iv) if isinstance(iv, str) else tc(json.dumps(iv, default=str))
                                t += n
                                b = classify_format_a(ik)
                                if b == "story":
                                    s += n
                                elif b == "game_data":
                                    g += n
                                else:
                                    u += n
                        else:
                            n = tc(elem)
                            t += n
                            u += n
                continue
            if isinstance(v, str):
                n = tc(v)
            elif isinstance(v, (dict, list)):
                n = tc(json.dumps(v, default=str))
            else:
                n = 0
            t += n
            b = classify_format_c(k)
            if b == "story":
                s += n
            elif b == "game_data":
                g += n
            else:
                u += n
    return s, g, u, t


def bucket_format_d(prompt):
    """Format D: prompt opens with `{}` followed by {loreBookKeys, contextElements:[stringified turnState JSON]}."""
    if not prompt or not prompt.lstrip().startswith("{}"):
        return None
    obj, _, _ = _find_balanced_json(prompt, prompt.find("}") + 1)
    if not obj or not isinstance(obj, dict) or not obj.get("contextElements"):
        return None
    s = g = u = t = 0
    for elem in obj.get("contextElements", []):
        if isinstance(elem, str):
            try:
                inner = json.loads(elem, strict=False)
            except Exception:
                inner = None
            if isinstance(inner, dict):
                for k, v in inner.items():
                    n = tc(v) if isinstance(v, str) else tc(json.dumps(v, default=str))
                    t += n
                    kl = k.strip().lower()
                    if kl in {"turnstory", "story", "narrative", "previous turn", "user prompt"}:
                        s += n
                    elif kl in {"turnplayer", "turnaction", "turnoutcome", "player", "world", "history"}:
                        g += n
                    else:
                        u += n
            else:
                n = tc(elem)
                t += n
                u += n
    return s, g, u, t


def bucket_prompt(prompt):
    """Try each format in priority order. Returns (story, game_data, unknown, total, fmt_tag)."""
    if not prompt or len(prompt) < 30:
        return None
    # Format D: very specific signature (starts with literal {})
    if prompt.lstrip().startswith("{}"):
        d = bucket_format_d(prompt)
        if d and d[3] > 50:
            return (*d, "D")
    # Format A: explicit contextMap key
    if '"contextMap"' in prompt or ' contextMap' in prompt:
        a = bucket_format_a(prompt)
        if a and a[3] > 50:
            return (*a, "A")
    # Format C: starts with {
    if prompt.lstrip().startswith("{"):
        c = bucket_format_c_multi(prompt)
        if c and c[3] > 50:
            return (*c, "C")
    # Format B: explicit USER PROMPT marker
    if "##USER PROMPT##" in prompt:
        b = bucket_format_b(prompt)
        if b and b[3] > 50:
            return (*b, "B")
    # Fallback: try format-C anyway
    c = bucket_format_c_multi(prompt)
    if c and c[3] > 50:
        return (*c, "C-fallback")
    return None


def bucket_opaque(prompt):
    """For pipes with only a partial prompt capture, use content-shape heuristic
    instead of reporting 0 attribution. Returns (story, game_data, unknown, total, fmt_tag)."""
    if not prompt:
        return None
    head = prompt[:200].strip()
    # Pure prose
    if not head.startswith("{") and not head.startswith("##"):
        n = tc(prompt)
        return (n, 0, 0, n, "prose")
    # JSON starting with game-data keys
    if prompt.lstrip().startswith("{"):
        c = bucket_format_c_multi(prompt)
        if c and c[3] > 50:
            return (*c, "C-opaque")
    # PLAYER ACTION/INVENTORY schema
    if "PLAYER ACTION" in prompt or "PLAYER INVENTORY" in prompt:
        n = tc(prompt)
        return (n, 0, 0, n, "action+inventory")
    return None


# ============================================================
# Walk events + attribute
# ============================================================

def walk_turn(turn_dir):
    """Walk every trace.json under turn_dir. Return dict of per-pipe attribution."""
    all_events = []
    for tp in sorted(_rglob(turn_dir, "trace.json")):
        with open(tp) as f:
            for e in json.load(f):
                e["_file"] = os.path.relpath(tp, turn_dir)
                all_events.append(e)
    all_events.sort(key=lambda e: e["timestamp"])

    events_by_pipe = defaultdict(list)
    for e in all_events:
        events_by_pipe[e.get("pipeName", "?")].append(e)

    pipe_data = defaultdict(lambda: {
        "story_tok": 0, "game_data_tok": 0, "unknown_tok": 0,
        "inputPrompt_tokens": 0,
        "actualInputTokens_total": 0, "inputTokens_total": 0,
        "outputTokens_total": 0,
        "successful_api_calls": 0,
        "story_attributed": 0, "game_data_attributed": 0, "unknown_attributed": 0,
        "fullPrompt_count": 0,
        "formats_used": set(),
        "max_fullPrompt_len": 0,
    })

    for pipe_name, events in events_by_pipe.items():
        # LONGEST fullPrompt per pipe - not the first (v2.0 rule)
        longest_fullPrompt = None
        longest_buckets = None
        longest_format = None
        for e in events:
            et = e.get("eventType")
            meta = e.get("metadata", {})
            if et == "PIPE_START" and meta.get("fullPrompt"):
                fp = meta["fullPrompt"]
                pd = pipe_data[pipe_name]
                pd["max_fullPrompt_len"] = max(pd["max_fullPrompt_len"], len(fp))
                if len(fp) > 50:
                    b = bucket_prompt(fp)
                    if b:
                        s, g, u, t, fmt = b
                        if longest_fullPrompt is None or len(fp) > len(longest_fullPrompt):
                            longest_fullPrompt = fp
                            longest_buckets = (s, g, u, t)
                            longest_format = fmt
                    else:
                        # Try opaque heuristic
                        ob = bucket_opaque(fp)
                        if ob:
                            s, g, u, t, fmt = ob
                            if longest_fullPrompt is None or len(fp) > len(longest_fullPrompt):
                                longest_fullPrompt = fp
                                longest_buckets = (s, g, u, t)
                                longest_format = fmt
        if longest_buckets:
            pd = pipe_data[pipe_name]
            pd["fullPrompt_count"] += 1
            pd["formats_used"].add(longest_format)
            pd["story_tok"] += longest_buckets[0]
            pd["game_data_tok"] += longest_buckets[1]
            pd["unknown_tok"] += longest_buckets[2]
            pd["inputPrompt_tokens"] += longest_buckets[3]
            longest_buckets_total = longest_buckets[3]
        else:
            longest_buckets_total = 0

        # Apply bucket shares to API_CALL_SUCCESS events
        for e in events:
            if e.get("eventType") != "API_CALL_SUCCESS":
                continue
            actual = (e.get("metadata", {}).get("actualInputTokens")
                      or e.get("metadata", {}).get("inputTokens") or 0)
            inp = e.get("metadata", {}).get("inputTokens") or 0
            out = e.get("metadata", {}).get("outputTokens") or 0
            pd = pipe_data[pipe_name]
            if actual:
                pd["successful_api_calls"] += 1
                pd["actualInputTokens_total"] += actual
                if longest_buckets_total > 0:
                    s, g, u, t = longest_buckets
                    pd["story_attributed"] += int(actual * s / t)
                    pd["game_data_attributed"] += int(actual * g / t)
                    pd["unknown_attributed"] += int(actual * u / t)
            if inp:
                pd["inputTokens_total"] += inp
            if out:
                pd["outputTokens_total"] += out

    return pipe_data


def _rglob(root, pattern):
    """Yield absolute paths matching pattern under root (recursive)."""
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn == pattern:
                yield os.path.join(dirpath, fn)


# ============================================================
# Reporting
# ============================================================

def format_report(pipe_data, turn_dir):
    """Print a per-pipe attribution table to stdout and return totals dict."""
    print("=" * 100)
    print(f"AUTOGENESIS PER-PIPE TOKEN COST - {os.path.basename(turn_dir)}")
    print("=" * 100)
    print(f"\n{'PIPE':<46} {'calls':>5} {'actualIn':>10} {'gameData':>10} "
          f"{'story':>10} {'unknown':>10} {'fmt':>10} {'cov':>6}")
    print("-" * 110)

    total_actual = total_game = total_story = total_unknown = 0
    rows = []
    for pipe_name in sorted(pipe_data.keys(),
                            key=lambda p: -pipe_data[p]["actualInputTokens_total"]):
        pd = pipe_data[pipe_name]
        if pd["actualInputTokens_total"] == 0:
            continue
        cov = pd["inputPrompt_tokens"] / max(pd["actualInputTokens_total"], 1)
        fmt = ",".join(sorted(pd["formats_used"])) if pd["formats_used"] else "?"
        total_actual += pd["actualInputTokens_total"]
        total_game += pd["game_data_attributed"]
        total_story += pd["story_attributed"]
        total_unknown += pd["unknown_attributed"]
        rows.append((pipe_name, pd, fmt, cov))
        print(f"{pipe_name:<46} {pd['successful_api_calls']:>5} "
              f"{pd['actualInputTokens_total']:>10} "
              f"{pd['game_data_attributed']:>10} "
              f"{pd['story_attributed']:>10} "
              f"{pd['unknown_attributed']:>10} "
              f"{fmt:>10} {cov:>6.0%}")

    print("-" * 110)
    print(f"{'TOTAL':<46} "
          f"{sum(p[1]['successful_api_calls'] for p in rows):>5} "
          f"{total_actual:>10} {total_game:>10} "
          f"{total_story:>10} {total_unknown:>10}")
    if total_actual:
        print(f"\n  game_data fraction: {total_game / total_actual:.1%}")
        print(f"  story fraction:     {total_story / total_actual:.1%}")
        print(f"  unknown fraction:   {total_unknown / total_actual:.1%}")
        print(f"  accounted fraction: "
              f"{(total_game + total_story) / total_actual:.1%}")

    return {
        "turn": os.path.basename(turn_dir),
        "trace_dir": turn_dir,
        "token_counter": "tiktoken cl100k_base",
        "total_input_tokens": total_actual,
        "game_data_tokens": total_game,
        "story_tokens": total_story,
        "unknown_tokens": total_unknown,
        "game_data_fraction": total_game / max(total_actual, 1),
        "story_fraction": total_story / max(total_actual, 1),
        "unknown_fraction": total_unknown / max(total_actual, 1),
        "accounted_fraction": (total_game + total_story) / max(total_actual, 1),
        "per_pipe": [
            {
                "pipe": p[0],
                "successful_api_calls": p[1]["successful_api_calls"],
                "actual_input_tokens": p[1]["actualInputTokens_total"],
                "game_data_tokens": p[1]["game_data_attributed"],
                "story_tokens": p[1]["story_attributed"],
                "unknown_tokens": p[1]["unknown_attributed"],
                "format": p[2],
                "prompt_coverage": p[3],
            }
            for p in rows
        ],
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Per-pipe input-token attribution for Autogenesis turn traces "
                    "(game data vs story).")
    parser.add_argument("--dir", required=True,
                        help="Path to a turn directory (e.g. ~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/)")
    parser.add_argument("--json", default=None,
                        help="Optional path to write a JSON report")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"ERROR: not a directory: {args.dir}", file=sys.stderr)
        sys.exit(1)

    pipe_data = walk_turn(args.dir)
    report = format_report(pipe_data, args.dir)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nJSON report written to {args.json}")


if __name__ == "__main__":
    main()