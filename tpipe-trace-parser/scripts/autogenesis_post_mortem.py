#!/usr/bin/env python3
"""
Autogenesis post-mortem extractor.

Reads a turn directory (e.g. ~/.tpipe/debug/trace/Round_1_Turn_2_Bigwang_McDouchebag/)
and prints a compact per-turn summary: action, validator verdict, narrative prose,
judge verdict, failures, and cascade turn detection.

Handles the three real-world extraction pitfalls:

1. CGO `author` pipe TRANSFORMATION_SUCCESS is mostly agent meta-reasoning.
   The actual readable narrative is in the LAST 1500-2500 chars.

2. AI Player Takeover's longest API_CALL_SUCCESS can be 240K+ chars of
   LLM conversation history. The actionable action is the LAST `agent` role's
   `content.text` inside the JSON `history` array.

3. NPC cascade turns have NO NeoWritingAgent, NO Judge, NO MaintenanceSplitter.
   Only NPC_* subfolders. Extract from NPC_Active_Turn and AI_Counter_Response.

Usage:
  python3 autogenesis_post_mortem.py <turn_dir> [<turn_dir> ...]
  python3 autogenesis_post_mortem.py ~/.tpipe/debug/trace/Round_*
"""
import json
import os
import re
import sys
import glob


def load(path):
    with open(path) as f:
        return json.load(f)


def get_text(e):
    c = e.get("content")
    return c.get("text", "") if isinstance(c, dict) else ""


def get_meta(e, key):
    m = e.get("metadata", {})
    return str(m.get(key, "")) if isinstance(m, dict) else ""


def extract_prose_from_author_pipe(events, min_total=2500, tail_chars=2500):
    """CGO author pipe: the narrative is in the LAST chars of TRANSFORMATION_SUCCESS."""
    cands = []
    for e in events:
        if e.get("eventType") == "TRANSFORMATION_SUCCESS":
            t = get_text(e)
            if t and len(t) >= min_total:
                cands.append((e.get("pipeName", ""), t))
    if not cands:
        return None
    cands.sort(key=lambda x: len(x[1]), reverse=True)
    pn, text = cands[0]
    return (pn, text[-tail_chars:])


def extract_prose_from_writing_pipe(events):
    """`writing pipe` (Shitty Bob case): entire TRANSFORMATION_SUCCESS is prose."""
    for e in events:
        if e.get("eventType") == "TRANSFORMATION_SUCCESS":
            if e.get("pipeName") == "writing pipe":
                t = get_text(e)
                if t and len(t) > 500:
                    return ("writing pipe", t)
    return None


def extract_player_action_from_validator(events):
    """First PIPE_START/TRANSFORMATION_START with substantial text in the validator."""
    best = None
    for e in events:
        if e.get("eventType") in ("PIPE_START", "TRANSFORMATION_START"):
            t = get_text(e)
            if 50 < len(t) < 5000:
                if best is None or len(t) > len(best[1]):
                    best = (e.get("pipeName", ""), t)
    return best


def extract_validator_verdict(events):
    """API_CALL_SUCCESS of `legality checker pipe` with JSON output."""
    for e in events:
        if e.get("eventType") == "API_CALL_SUCCESS":
            pn = e.get("pipeName", "").lower()
            if "legality" in pn or "validator" in pn or "checker" in pn:
                t = get_text(e).strip()
                if t.startswith("{"):
                    try:
                        return json.loads(t)
                    except Exception:
                        pass
    return None


def extract_ai_player_action(events):
    """AI Player Takeover: last `agent` role text in the LLM history JSON.

    The longest API_CALL_SUCCESS of `Execution Stage` or `Synthesis Stage`
    is often 240K+ chars of full LLM conversation. Parse it as JSON and
    pull the last agent-role text.
    """
    for stage in ("Execution Stage", "Synthesis Stage"):
        cands = []
        for e in events:
            if e.get("eventType") in ("API_CALL_SUCCESS", "TRANSFORMATION_SUCCESS"):
                if stage in e.get("pipeName", ""):
                    t = get_text(e)
                    if t:
                        cands.append((e.get("pipeName", ""), t))
        if not cands:
            continue
        cands.sort(key=lambda x: len(x[1]), reverse=True)
        _, text = cands[0]
        try:
            data = json.loads(text)
            history = data.get("history", [])
            for entry in reversed(history):
                if entry.get("role") == "agent":
                    content = entry.get("content", {})
                    if isinstance(content, dict):
                        agent_text = content.get("text", "")
                        if agent_text:
                            return (stage, agent_text[:2000])
            if "characterProfile" in data or "problemView" in data:
                sol = data.get("characterSolution", {})
                if isinstance(sol, dict):
                    return (stage, sol.get("proposedApproach", "")[:2000] or json.dumps(data)[:2000])
        except (json.JSONDecodeError, TypeError):
            pass
        if len(text) < 5000:
            return (stage, text)
        return (stage, text[-2000:])
    return None


def extract_judge_verdict(events):
    """Last API_CALL_SUCCESS with reasoningConclusion in reasoningContent."""
    last = None
    for e in events:
        if e.get("eventType") == "API_CALL_SUCCESS":
            m = e.get("metadata", {})
            rc = m.get("reasoningContent", "") if isinstance(m, dict) else ""
            if isinstance(rc, str) and rc:
                match = re.search(r'"reasoningConclusion"\s*:\s*"([^"]{50,3000})"', rc)
                if match:
                    last = (e.get("pipeName", ""), match.group(1))
    return last


def extract_failures(events, source):
    out = []
    for e in events:
        t = e.get("eventType", "")
        if "FAILURE" in t or "TIMEOUT" in t or t == "ERROR":
            err = ""
            m = e.get("metadata", {})
            if isinstance(m, dict):
                err = m.get("error", "")
            out.append((source, t, e.get("pipeName", "?"), str(err)[:200]))
    return out


def detect_cascade_turn(turn_dir):
    """Cascade turn: no NeoWritingAgent, no Judge, but has NPC_Active_Turn."""
    has_writing = os.path.isdir(os.path.join(turn_dir, "NeoWritingAgent"))
    has_judge = os.path.isdir(os.path.join(turn_dir, "Judge"))
    has_npc_active = os.path.isdir(os.path.join(turn_dir, "NPC_Active_Turn"))
    return (not has_writing) and (not has_judge) and has_npc_active


def extract_cascade_turn(turn_dir):
    """Extract NPC action + target player + counter-response from a cascade turn."""
    target = "?"
    cascade_dir = glob.glob(os.path.join(turn_dir, "NPC_CascadeTargetDetector_*_Depth*"))
    if cascade_dir:
        m = re.search(r"NPC_CascadeTargetDetector_(.+?)_Depth\d+", os.path.basename(cascade_dir[0]))
        if m:
            target = m.group(1)

    npc_action = None
    npc_path = os.path.join(turn_dir, "NPC_Active_Turn", "trace.json")
    if os.path.exists(npc_path):
        events = load(npc_path)
        for e in events:
            if e.get("eventType") == "PIPE_SUCCESS":
                pn = e.get("pipeName", "").lower()
                if "npc actor" in pn:
                    t = get_text(e)
                    if t and len(t) > 200:
                        npc_action = (e.get("pipeName", ""), t)
                        break

    counter = None
    ai_counter_glob = glob.glob(os.path.join(turn_dir, "AI_Counter_Response", "*.json"))
    if ai_counter_glob:
        try:
            events = load(ai_counter_glob[0])
            for e in reversed(events):
                if e.get("eventType") in ("PIPE_SUCCESS", "TRANSFORMATION_SUCCESS", "API_CALL_SUCCESS"):
                    t = get_text(e)
                    if t and 200 < len(t) < 5000:
                        counter = (e.get("pipeName", ""), t[:1500])
                        break
        except Exception as ex:
            counter = (None, f"<error reading counter: {ex}>")

    return {
        "target_player": target,
        "npc_action": npc_action,
        "counter_response": counter,
    }


def process_turn(turn_dir):
    name = os.path.basename(turn_dir.rstrip("/"))
    print(f"\n{'='*70}\n{name}\n{'='*70}")
    failures = []

    if detect_cascade_turn(turn_dir):
        print("\n>>> CASCADE TURN (no NeoWritingAgent/Judge, NPC counter-response in flight)")
        info = extract_cascade_turn(turn_dir)
        print(f"Target player: {info['target_player']}")
        if info["npc_action"]:
            print(f"\n--- NPC ACTION ({info['npc_action'][0]}) ---")
            print(info['npc_action'][1][:1500])
        if info["counter_response"]:
            print(f"\n--- TARGET COUNTER ({info['counter_response'][0]}) ---")
            print(info['counter_response'][1][:1500])
        return failures

    val_dirs = glob.glob(os.path.join(turn_dir, "ValidationSplitter", "*", "validator"))
    action_text = None
    verdict = None
    for vd in val_dirs:
        p = os.path.join(vd, "trace.json")
        if not os.path.exists(p):
            continue
        events = load(p)
        a = extract_player_action_from_validator(events)
        if a and (not action_text or len(a[1]) > len(action_text)):
            action_text = a[1]
        v = extract_validator_verdict(events)
        if v and not verdict:
            verdict = v
        failures.extend(extract_failures(events, f"{name}/validator"))

    ai_path = os.path.join(turn_dir, "AI_Player_Takeover", "trace.json")
    if os.path.exists(ai_path):
        events = load(ai_path)
        a = extract_ai_player_action(events)
        if a and not action_text:
            action_text = a[1]
        failures.extend(extract_failures(events, f"{name}/AI_Player_Takeover"))

    if action_text:
        print(f"\n--- ACTION ---")
        print(action_text[:1200])
        if len(action_text) > 1200:
            print(f"[...+{len(action_text)-1200} chars]")

    if verdict:
        print(f"\n--- VALIDATOR VERDICT ---")
        print(f"  isLegal: {verdict.get('isLegal')}")
        print(f"  captureAttempted: {verdict.get('captureAttempted')}")

    narr_path = os.path.join(turn_dir, "NeoWritingAgent", "trace.json")
    if os.path.exists(narr_path):
        events = load(narr_path)
        prose = extract_prose_from_writing_pipe(events) or extract_prose_from_author_pipe(events)
        if prose:
            print(f"\n--- NARRATIVE ({prose[0]}) ---")
            print(prose[1][:1500])
            if len(prose[1]) > 1500:
                print(f"[...+{len(prose[1])-1500} chars]")
        failures.extend(extract_failures(events, f"{name}/NeoWritingAgent"))

    judge_path = os.path.join(turn_dir, "Judge", "trace.json")
    if os.path.exists(judge_path):
        events = load(judge_path)
        j = extract_judge_verdict(events)
        if j:
            print(f"\n--- JUDGE VERDICT ({j[0]}) ---")
            print(j[1][:800])
        failures.extend(extract_failures(events, f"{name}/Judge"))

    if failures:
        print(f"\n--- FAILURES ({len(failures)}) ---")
        for f in failures[:5]:
            print(f"  [{f[0]}] {f[1]} in {f[2]}: {f[3]}")
        if len(failures) > 5:
            print(f"  ...+{len(failures)-5} more")
    else:
        print(f"\n[no failures]")

    return failures


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 autogenesis_post_mortem.py <turn_dir> [...]", file=sys.stderr)
        sys.exit(1)
    for arg in sys.argv[1:]:
        if "*" in arg or "?" in arg:
            import subprocess
            result = subprocess.run(
                ["bash", "-c", f"ls -d {arg}"],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().split("\n"):
                if line:
                    process_turn(line.strip())
        else:
            process_turn(arg)
