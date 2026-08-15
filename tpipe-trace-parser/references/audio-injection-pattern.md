# audioTracks injection — the world-snapshot leak that inflated traces

## Symptom

A previously-shipped pricing/cost artifact claims per-turn input tokens 2-3x higher than a fresh `extract_pipeline.py` run shows on the same trace directory. Per-turn cost in the $0.20-$0.50 range when the actual per-turn cost is in the $0.05-$0.15 range. Every cost projection downstream is wrong by the same factor.

## Confirmed case (2026-07-25)

The autogenesis margin report v1 was built from `~/.tpipe/autogenesis-trace/Round_1_Turn_*/` traces captured while a bug was injecting the full music catalog into every world-state serializer that fed LLM context. Per-turn input tokens were inflated ~2x. The v1 PDF said $4.31/game @ E[12 rounds] — actual was $3.25. The v1 said $0.32/turn — actual was $0.0966.

## Root cause

`server/src/main/kotlin/agent/debugTrace/WorldTokenTrace.kt:156` serializes every top-level field on `World` for the diagnostic report. The `audioTracks` field is included. The world-state serializer used by every pipe's prompt (the *consumer* side, not the diagnostic side) was pulling the same full audio catalog — 8 music categories × N tracks per category — into every prompt.

```kotlin
// server/src/main/kotlin/agent/debugTrace/WorldTokenTrace.kt:142-159
fun serializeFields(world: World): List<FieldTokenCount>
{
    val entries = mutableListOf<FieldTokenCount>()
    entries += encodeField("name", world.name)
    entries += encodeField("storyScenario", world.storyScenario)
    // ...
    entries += encodeField("mapTiles", world.mapTiles)
    entries += encodeField("activePlayers", world.activePlayers)
    entries += encodeField("npc", world.npc)
    // ...
    entries += encodeField("audioTracks", world.audioTracks)        // <-- LINE 156
    entries += encodeField("mutex", world.mutex, includeInReport = false)
    return entries
}
```

The diagnostic side at line 156 is fine — that's the field-contribution report for the operator. The bug was the consumer side: any world-state serializer that pulled `world.audioTracks` into the prompt. The fix removed the audio catalog from the LLM-facing serializer while keeping it in the diagnostic serializer.

## How to detect this class of bug in a new session

If a derived artifact (PDF, dashboard, pricing model) built from traces shows inflated numbers that don't match a fresh re-extraction, run this grep:

```bash
# Look for world-snapshot serialization code in server
grep -rn "encodeField\|world.audioTracks\|audioTracks" \
    /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/ \
    | grep -v "\.bak\|build/" | head -30
```

Specifically look for:
- `audioTracks` references inside `*Prompt*.kt` files — these are likely leaking the catalog into prompts.
- `world.audioTracks` in any serializer other than `WorldTokenTrace.kt` — likely a second consumer that needs to drop the field.
- `MusicTrackCatalog` referenced from prompt-building files — confirms the bug path.

## Verification recipe

```bash
# Re-extract from the most recent traces
python3 /home/cage/.hermes/skills/software-development/tpipe-trace-parser/scripts/extract_pipeline.py \
    --dir /home/cage/.tpipe/autogenesis-trace/Round_1_Turn_3_Ogadi_Okwengu \
    --output /tmp/verify.json

# Read the per-call bucket
python3 -c "import json; r=json.load(open('/tmp/verify.json')); print('per-call input:', r['aggregate_token_totals']['inputTokens']['total'])"
# Expected post-fix: ~1.5M-2.5M input tokens per turn for autogenesis human turns
# Pre-fix (bug present): ~3M-5M input tokens per turn (audio catalog doubled the world snapshot)

# Compare against cumulative
python3 -c "import json; r=json.load(open('/tmp/verify.json')); print('cumulative totalInput:', r['aggregate_token_totals']['totalInputTokens']['total'])"
# Ratio should be 1.0x-1.6x (cumulative is per-call plus the cumulative-tracker emissions)
# If ratio is higher, the cumulative bucket is double-counting across nested pipe scopes
```

## What the actual fix looked like

The fix was on the consumer side: the world-state serializer used by pipe prompts (NOT `WorldTokenTrace.kt`) dropped `audioTracks` from the serialized fields. The diagnostic serializer at `WorldTokenTrace.kt:156` kept `audioTracks` because the operator wants to see the field-contribution breakdown for debugging.

If a future session sees the same symptom — derived artifact inflated by ~2x, fresh extraction shows ~half the input token count — run the grep above. The fix is removing `audioTracks` (or the next suspicious high-cardinality field) from the LLM-facing serializer, not from the diagnostic one.

## Related files

- `server/src/main/kotlin/agent/debugTrace/WorldTokenTrace.kt:156` — diagnostic serializer (KEEP audioTracks)
- `server/src/main/kotlin/gameInit/GameInit.kt:235-251` — audio-tracks loader, fallthrough behavior
- `server/src/main/kotlin/gameState/WorldManager.kt:2134-2183` — audio-tracks installation onto world state
- `server/src/main/kotlin/org/ttt/autogenesis/server/audio/` — MusicSelector, MusicTrackCatalog, AudioTracksResourceLoader
- `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt:108-116` — per-turn music picker (does NOT feed LLM context; the catalog lives here for the runtime audio system)
