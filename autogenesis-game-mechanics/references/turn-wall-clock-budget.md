# Turn Wall-Clock Budget — Empirical Reference

Measured from `~/.tpipe/debug/trace/<turn-directory>/` turn directories. Each turn produces one `trace.json` per sub-pipeline (Judge, TargetDetectors, WritingAgents, etc.); wall-clock = `max(end_ts) - min(start_ts)` across all subtraces.

## Per-archetype budget

| Archetype | Trace | Subtraces | Wall-clock | LLM calls | Avg/turn (s) |
|---|---|---:|---:|---:|---:|
| Human player | `Round_3_Turn_0_Lord_Maple_Tree/` | 7 | 274.9 s | 29 | — |
| Human player | `Round_4_Turn_0_Lord_Maple_Tree/` | 8 | 250.3 s | 30 | — |
| **Human player (avg)** | | | **262.6 s** | **~30** | **262.6 + 90 = 353 s** |
| NPC | `Round_3_Turn_1_Syrup_Whisperer/` | 10 | 365.6 s | 58 | 365.6 s |
| AI player | `Round_3_Turn_2_Robert/` | 7 | 814.4 s | 31 | 814.4 s |

**Plus a 90 s planning estimate per human turn** (player input time — NOT in trace). Brings a human turn to ~5.9 min.

## Caveats

- **NPC R3T1 = 58 LLM calls is unusually high.** Syrup Whisperer's turn included narrative cascade work a normal NPC turn wouldn't do. **6.09 min is an upper bound for NPC archetype.**
- **AI R3T2 = 814.4 s includes one cancelled `mantle author 31b` retry** (111,752 input tokens wasted). A clean AI turn is probably 600-700 s (10-12 min), not 13.6 min.
- **Human input time (90 s) is a planning estimate.** Not measured. Real range: 30 s (rushed click) to 5+ min (deep play). The traces capture server-side activity only.
- **Network latency not modeled.** Estimate 5-15 s per LLM call if needed.
- **N=1 for NPC and AI archetypes.** Two human observations give ~10% variance confidence. The NPC/AI figures would tighten with more samples.

## Parallel speedup observed

R3T0 subtrace sum = 332.3 s; wall-clock = 274.9 s → **1.21× parallel speedup** (17% of subtrace time is overlap).

`TurnResolutionSplitter` and `NeoWritingAgent` ran in parallel during R3T0. So per-pipe orchestration already includes modest parallel speedup — **don't** apply an additional speedup factor on top of these figures.

## Recipe: compute wall-clock for any turn directory

```python
import json, os

turn_dir = "<path to ~/.tpipe/debug/trace/Round_X_Turn_Y_Actor/>"
starts, ends = [], []
api_dur_ms = 0
api_count = 0

for name in sorted(os.listdir(turn_dir)):
    p = os.path.join(turn_dir, name, 'trace.json')
    if not os.path.isfile(p): continue
    data = json.load(open(p))
    if not data: continue
    ts = [e['timestamp'] for e in data if 'timestamp' in e]
    if len(ts) >= 2:
        starts.append(ts[0]); ends.append(ts[-1])
    # Pair API_CALL_START → API_CALL_SUCCESS by pipeId (not pipeName — pipes nest)
    call_starts = {}
    for e in data:
        et = e.get('eventType', '')
        pid = e.get('pipeId', '')
        if et == 'API_CALL_START':
            call_starts[pid] = e['timestamp']
        elif et == 'API_CALL_SUCCESS' and pid in call_starts:
            api_dur_ms += e['timestamp'] - call_starts.pop(pid)
            api_count += 1

wall_s = (max(ends) - min(starts)) / 1000
sum_subtrace_s = sum((e-s)/1000 for s, e in zip(starts, ends))  # approximation
print(f"Wall-clock: {wall_s:.1f}s")
print(f"Subtrace sum: {sum_subtrace_s:.1f}s")
print(f"API call count: {api_count}, sum: {api_dur_ms/1000:.1f}s")
```

## Per-game wall-clock projection

Formula:

```python
TURN_WALL_S = { "human": 262.6 + 90, "npc": 365.6, "ai": 814.4 }  # seconds
NPC_SLOTS_PER_ROUND = 1.75  # weighted slot roll from TurnHarness.kt:3162-3191
                         # = 1*0.50 + 2*0.30 + 3*0.15 + 4*0.05

def game_wallclock_minutes(rounds, n_human, n_ai, n_npc):
    per_round = (n_human * TURN_WALL_S["human"]
               + n_ai    * TURN_WALL_S["ai"]
               + n_npc   * TURN_WALL_S["npc"]
               + NPC_SLOTS_PER_ROUND * TURN_WALL_S["npc"])
    return (per_round * rounds) / 60
```

## Per-game wall-clock at every end-round threshold (hours)

| Config | R5 | R12 | R22 | R25 (cap) | Expected* |
|---|---:|---:|---:|---:|---:|
| 4 humans | 2.85 | 6.84 | 12.54 | 14.25 | **11.95** |
| 2 humans + 2 AI | 4.13 | 9.91 | 18.18 | 20.66 | **17.32** |
| 1 human + 3 AI | 4.77 | 11.45 | 20.99 | 23.86 | **20.01** |
| 1 human + 3 NPC | 2.90 | 6.97 | 12.78 | 14.52 | **12.18** |

*Expected* = weighted by projected ending distribution: R1-5: 5%, R6-10: 8%, R11-15: 8%, R16-20: 7%, R21-24: 5%, R25: 67% (midpoints of each bucket).

## Cost × time matrix headline

| Mode | Cost/game (R25 mid) | Hours/game | $/hr |
|---|---:|---:|---:|
| 4P / player | $4.00 | 14.2 | $0.28 |
| 1v1 | $8.00 | 12.5 | $0.64 |
| 1v3 | $16.01 | 14.5 | **$1.10** |

(Live numbers update with the controls in `tools/autogenesis_subscription_model.html` — at-a-glance stats panel + cost × wall-clock matrix + tier burn-rate table.)

## Headline numbers

- A full R25-cap 4-human multiplayer game: **~14 hours** of wall-clock.
- A full R25-cap 1H+3AI game: **~24 hours** (AI turns are 3× slower than human turns because of the synthesis + planning + execution pipeline).
- Expected game duration (with early-ending probability): **12-20 hours** depending on player composition.

## Trace → cost×time workflow

1. Pick a turn archetype (human/NPC/AI player) — use the values above.
2. Multiply by mode multiplier for 1v1 (2×) or 1v3 (4×) — wall-clock doesn't scale with cost multiplier; per-game cost does.
3. Add NPC slot-roll overhead: `NPC_SLOTS_PER_ROUND × npc_turn_wall × rounds` to total.
4. To get expected game duration, weight each ending bucket by its prior probability from the prior endgame-projection session.
5. Divide total game cost by total hours to get $/hr inference burn rate.

## Cross-reference

- Game-end mechanics: see skill `autogenesis-game-mechanics` SKILL.md § "Victory Conditions & Win Thresholds"
- Token-cost basis: see skill `tpipe-trace-parser` references
- NPC slot roll distribution: `TurnHarness.kt:3162-3173` (1 slot × 50%, 2 × 30%, 3 × 15%, 4 × 5%)