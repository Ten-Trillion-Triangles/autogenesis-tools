#!/usr/bin/env python3
"""Memory sampler for Autogenesis game servers during a playtest.

Polls RSS, VmPeak, VmHWM, threads, jcmd GC.heap_info, and (when enabled)
jcmd VM.native_memory for both the game server and server-extend. Designed
for AccelByte deployment sizing — answers "what's the minimum server size
I need to allocate?"

Usage:
    python3 memory_sampler.py <game_pid> <extend_pid> <out.csv> [interval_sec]

Environment variables:
    PHASE_FILE  Path to a text file the controller writes phase markers to
                (e.g. /tmp/lmt_mem_phase.txt). The current phase string is
                captured in every row so memory spikes can be correlated
                with game events (round-N-turn, round-N-narrative, etc.).
                Default: /tmp/lmt_mem_phase.txt

Typical workflow:
    1. Start server-extend + game server, capture PIDs from `ss -tlnp`
    2. Start this sampler in background:
         python3 scripts/memory_sampler.py <game_pid> <extend_pid> mem.csv 2 &
    3. Run the controller:
         /tmp/autogenesis-dev/bin/python controller.py --no-ui
    4. Controller writes phase markers to PHASE_FILE between turns
    5. After N rounds, kill controller + sampler, analyse mem.csv:
         - `python3 -c "import pandas as pd; df=pd.read_csv('mem.csv'); ..."`
         - or just `awk -F, 'NR>1 {print $1,$3,$9}' mem.csv` for quick eyeball

Columns written (in order):
    ts_utc                ISO-8601 UTC timestamp of the sample
    phase                 Phase marker from PHASE_FILE at sample time
    game_rss_kb           Game server RSS (VmRSS from /proc/<pid>/status)
    game_vmsize_kb        Game server virtual size (VmSize)
    game_vmpeak_kb        Game server peak virtual size (VmPeak)
    game_vmhwm_kb         Game server peak RSS (VmHWM)
    game_threads          Game server thread count
    extend_rss_kb         server-extend RSS
    extend_vmsize_kb      server-extend virtual size
    extend_vmpeak_kb      server-extend peak virtual size
    extend_vmhwm_kb       server-extend peak RSS
    extend_threads        server-extend thread count
    game_heap_reserved_kb G1GC reserved heap
    game_heap_committed_kb G1GC committed heap
    game_heap_used_kb     G1GC used (post-GC)
    extend_heap_reserved_kb
    extend_heap_committed_kb
    extend_heap_used_kb
    game_native_reserved_kb   (only if -XX:NativeMemoryTracking=summary is set)
    game_native_committed_kb  (only if NMT is set)

Notes:
- VSZ (VmSize) is huge (~21 GB) because the JVM pre-reserves the entire
  G1 heap region in virtual address space. RSS (VmRSS / VmHWM) is the
  number that matters for AccelByte sizing — that's physical RAM.
- Heap "reserved" is the G1 region's full address range. "committed" is
  what the OS has actually backed with pages. "used" is post-GC.
- NMT (Native Memory Tracking) is OFF by default in Gradle's run config.
  If you want native memory breakdown, add to gradle.properties:
    org.gradle.jvmargs=-XX:NativeMemoryTracking=summary
  then restart the game server. The sampler auto-detects NMT state.
- A 2-second interval gives ~30 samples per minute. For a 2-round playtest
  (~10 minutes total), that's ~300 rows — small enough to load in pandas
  and big enough to catch sub-minute spikes.
"""
import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

GAME_PID = int(sys.argv[1])       # game server (port 9080)
EXTEND_PID = int(sys.argv[2])     # server-extend (port 7070)
OUT_CSV = sys.argv[3]             # output CSV path
INTERVAL = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
PHASE_FILE = os.environ.get("PHASE_FILE", "/tmp/lmt_mem_phase.txt")


def proc_status_kb(pid, key):
    """Read /proc/<pid>/status field (kB). Returns None if process gone."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith(key + ":"):
                    return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError, ValueError):
        return None
    return None


def jcmd_heap(pid):
    """jcmd <pid> GC.heap_info — extract used/committed/reserved K."""
    try:
        out = subprocess.check_output(
            ["jcmd", str(pid), "GC.heap_info"],
            stderr=subprocess.STDOUT, timeout=5,
        ).decode()
        m = re.search(r"reserved\s+(\d+)K,\s+committed\s+(\d+)K,\s+used\s+(\d+)K", out)
        if m:
            return {
                "heap_reserved_kb": int(m.group(1)),
                "heap_committed_kb": int(m.group(2)),
                "heap_used_kb": int(m.group(3)),
            }
    except Exception:
        pass
    return {"heap_reserved_kb": None, "heap_committed_kb": None, "heap_used_kb": None}


def jcmd_native(pid):
    """jcmd <pid> VM.native_memory summary — extract Total row if NMT enabled."""
    try:
        out = subprocess.check_output(
            ["jcmd", str(pid), "VM.native_memory", "summary"],
            stderr=subprocess.STDOUT, timeout=10,
        ).decode()
        if "disabled" in out.lower():
            return {"native_tracking": "disabled"}
        m = re.search(r"Total:\s*reserved=(\d+)KB,\s*committed=(\d+)KB", out)
        if m:
            return {
                "native_tracking": "enabled",
                "native_reserved_kb": int(m.group(1)),
                "native_committed_kb": int(m.group(2)),
            }
    except Exception:
        pass
    return {"native_tracking": "unknown"}


def read_phase():
    """Read phase marker text from PHASE_FILE. Stripped. 'unknown' if missing."""
    try:
        with open(PHASE_FILE) as f:
            return f.read().strip() or "unknown"
    except FileNotFoundError:
        return "no-phase-file"


def sample():
    ts = datetime.now(timezone.utc).isoformat()
    row = {
        "ts_utc": ts,
        "phase": read_phase(),
        "game_rss_kb":     proc_status_kb(GAME_PID, "VmRSS"),
        "game_vmsize_kb":  proc_status_kb(GAME_PID, "VmSize"),
        "game_vmpeak_kb":  proc_status_kb(GAME_PID, "VmPeak"),
        "game_vmhwm_kb":   proc_status_kb(GAME_PID, "VmHWM"),
        "game_threads":    proc_status_kb(GAME_PID, "Threads"),
        "extend_rss_kb":   proc_status_kb(EXTEND_PID, "VmRSS"),
        "extend_vmsize_kb":proc_status_kb(EXTEND_PID, "VmSize"),
        "extend_vmpeak_kb":proc_status_kb(EXTEND_PID, "VmPeak"),
        "extend_vmhwm_kb": proc_status_kb(EXTEND_PID, "VmHWM"),
        "extend_threads":  proc_status_kb(EXTEND_PID, "Threads"),
    }
    row.update({f"game_{k}": v for k, v in jcmd_heap(GAME_PID).items()})
    row.update({f"extend_{k}": v for k, v in jcmd_heap(EXTEND_PID).items()})
    nat = jcmd_native(GAME_PID)
    if nat.get("native_tracking") == "enabled":
        row["game_native_reserved_kb"] = nat["native_reserved_kb"]
        row["game_native_committed_kb"] = nat["native_committed_kb"]
    return row


def main():
    print(
        f"[mem-sampler] game_pid={GAME_PID} extend_pid={EXTEND_PID} "
        f"interval={INTERVAL}s csv={OUT_CSV} phase_file={PHASE_FILE}",
        flush=True,
    )
    write_header = not os.path.exists(OUT_CSV)
    f = open(OUT_CSV, "a", newline="", buffering=1)
    writer = None
    start = time.time()
    samples = 0
    try:
        while True:
            row = sample()
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if write_header:
                    writer.writeheader()
                    write_header = False
            writer.writerow(row)
            samples += 1
            elapsed = time.time() - start
            if samples % 15 == 0:
                grss = (row['game_rss_kb'] or 0) / 1024
                gheap = (row['game_heap_used_kb'] or 0) / 1024
                er = (row['extend_rss_kb'] or 0) / 1024
                print(
                    f"[mem-sampler] t={elapsed:6.1f}s "
                    f"phase={row['phase']:24s} "
                    f"game_rss={grss:6.0f}MB heap={gheap:6.0f}MB "
                    f"extend_rss={er:6.0f}MB",
                    flush=True,
                )
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print(
            f"[mem-sampler] Stopped after {samples} samples "
            f"over {time.time()-start:.0f}s",
            flush=True,
        )
    finally:
        f.close()


if __name__ == "__main__":
    main()
