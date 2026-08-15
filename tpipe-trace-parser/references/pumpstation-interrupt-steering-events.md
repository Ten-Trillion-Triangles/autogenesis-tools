# PumpStation Interrupt & Steering Events — capture reference

This reference covers three events added in the steering/interrupt feature wave (commits 023ce5fe and adjacent). The parser MUST handle these correctly; the previous parser silently dropped them as garbage keys.

## The new events

| Event | Source location (PumpStationHelpers.kt) | Metadata emitted |
|-------|------------------------------------------|------------------|
| `PUMP_STATION_STEERING_INJECTED` | `is SteeringInjected ->` branch | flat: `boundaryPhase`, `persistent`, `injectionId` + nested envelope `steering` (4 fields) + `contentPreview` |
| `PUMP_STATION_INTERRUPT_FIRED` | `is InterruptFired ->` branch | flat: `boundaryPhase`, `wasRewound`, `injectionId` + nested envelope `interrupt` (4 fields) + `contentPreview` |
| `PUMP_STATION_INTERRUPT_OVERFLOW_DROPPED` | `is InterruptOverflowDropped ->` branch | flat: `boundaryPhase`, `droppedCount`, `firstDroppedText` (no envelope) |

## The bug the parser had to fix

The visualizer renders nested metadata maps as a "psuedo-envelope" HTML pattern (this is a visualizer quirk, not a real envelope):

```html
<!-- Parent row with placeholder value -->
<div class='ps-meta-row'>
  <span class='ps-meta-key'>steering:</span>
  <span class='ps-meta-val'>{envelope: 4 field(s)}</span>
</div>

<!-- Envelope children, one per nested field, with class 'ps-meta-row-envelope' -->
<div class='ps-meta-row ps-meta-row-envelope'>
  <span class='ps-meta-key'>&nbsp;&nbsp;steering.phase:</span>
  <span class='ps-meta-val'>BeforeJudge</span>
</div>
<div class='ps-meta-row ps-meta-row-envelope'>
  <span class='ps-meta-key'>&nbsp;&nbsp;steering.persistent:</span>
  <span class='ps-meta-val'>false</span>
</div>
<div class='ps-meta-row ps-meta-row-envelope'>
  <span class='ps-meta-key'>&nbsp;&nbsp;steering.injectionId:</span>
  <span class='ps-meta-val'>dcfb0c54-3357-4f92-97a8-2def59a4d5db</span>
</div>
<div class='ps-meta-row ps-meta-row-envelope'>
  <span class='ps-meta-key'>&nbsp;&nbsp;steering.timestamp:</span>
  <span class='ps-meta-val'>1784934713664</span>
</div>
```

The previous parser captured these as 4 separate flat keys with `&nbsp;&nbsp;` prefixes (e.g. `&nbsp;&nbsp;steering.phase: BeforeJudge`). The placeholder `{envelope: 4 field(s)}` was also captured as a real value. The nested map was never assembled.

## The fix (parse_html_trace.py)

Three new regexes + a new helper `_parse_pumpstation_meta`:

```python
_PS_ENVELOPE_ROW_RE = re.compile(
    r"<div class=['\"]ps-meta-row\s+ps-meta-row-envelope['\"]>\s*"
    r"<span class=['\"]ps-meta-key['\"]>(&nbsp;)*([^<]+)</span>\s*"
    r"<span class=['\"]ps-meta-val['\"]>([^<]*)</span>\s*</div>",
    re.DOTALL,
)
_PS_PARENT_PLACEHOLDER_RE = re.compile(
    r"<div class=['\"]ps-meta-row['\"]>\s*"
    r"<span class=['\"]ps-meta-key['\"]>([^<]+):</span>\s*"
    r"<span class=['\"]ps-meta-val['\"]>\{envelope:[^}]*\}</span>\s*</div>",
    re.DOTALL,
)
```

The helper does exactly 4 steps in order:

1. Strip the parent placeholder rows (`<div class='ps-meta-row'>...{envelope: N}...</div>`) — otherwise the flat-row regex would capture the placeholder value.
2. Capture envelope children rows FIRST — they hold the real nested data. The `&nbsp;&nbsp;` prefix is grouped but discarded; the dotted key is split on the first `.` to separate parent from child.
3. Strip the envelope rows from the body before flat-row matching — otherwise the `&nbsp;&nbsp;` keys leak through as garbage.
4. Splice the envelope children into `meta` as a nested dict under the parent key.

**Order matters**: capture before strip. If you strip first, the data is gone.

## Expected output shape

After the fix, parsing `pumpstation-ps-178493471.html` (a real trace with `PUMP_STATION_STEERING_INJECTED`) produces:

```json
{
  "eventType": "PUMP_STATION_STEERING_INJECTED",
  "metadata": {
    "boundaryPhase": "BeforeJudge",
    "persistent": "false",
    "injectionId": "dcfb0c54-3357-4f92-97a8-2def59a4d5db",
    "contentPreview": "user just asked: focus on memory overhead, not throughput",
    "steering": {
      "phase": "BeforeJudge",
      "persistent": "false",
      "injectionId": "dcfb0c54-3357-4f92-97a8-2def59a4d5db",
      "timestamp": "1784934713664"
    }
  }
}
```

No `&nbsp;&nbsp;` keys. No `{envelope: N}` placeholder. Nested `steering` dict matches the source's `baseMetadata["steering"] = mapOf(...)` from `PumpStationHelpers.kt:24816`.

## Where to find real artifacts

The steering/interrupt live tests already generate traces with these events:

- `~/.tpipe/debug/trace/tpipe-config-steering-live/pumpstation-ps-NNNNNN.html` — contains `PUMP_STATION_STEERING_INJECTED`
- `~/.tpipe/debug/trace/tpipe-config-interrupt-live/pumpstation-ps-NNNNNN.html` — contains `PUMP_STATION_INTERRUPT_FIRED`

`PUMP_STATION_INTERRUPT_OVERFLOW_DROPPED` only fires when an actual overflow occurs. As of 2026-07-24 no on-disk trace has it — parser handles it because the source emission is flat (no envelope), but verification against a real artifact is pending.

## Live test env vars

To regenerate real traces with these events:

```bash
export TPIPE_LIVE_LLM_TEST="true"
export MINIMAX_API_KEY="<from .bashrc>"
export MINIMAX_BASE_URL="https://api.minimax.io/v1"
export tpipe_allowInsecureBaseUrl="true"
./gradlew :test --tests "com.TTT.Pipeline.PumpStationSteeringInterruptLiveTest" --rerun-tasks
```

This produces traces under `~/.tpipe/debug/trace/tpipe-config-{steering,interrupt}-live/`.

## Verification cases

The 10 pinned cases in `verify_extraction.py` now include:

- `pumpstation-steering` — requires `PUMP_STATION_STEERING_INJECTED` in `expect_event_types_subset`
- `pumpstation-interrupt` — requires `PUMP_STATION_INTERRUPT_FIRED` in `expect_event_types_subset`

If a future change reintroduces `&nbsp;&nbsp;` keys or drops the nested envelope, these cases fail immediately.
