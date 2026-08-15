# Pitfall — Agent result text hidden in the metadata soup

**Captured 2026-07-08 from a TPipe trace enhancement session.** The user asked: *"We have icons showing they ran, but no results of what exactly they did."* The user had PumpStation HTML reports open in a browser and could see per-event icons (👤 Foreground Agent, ⚖ Judge, 🛤 Dispatch, etc.) plus token chips and a `View content (N chars)` collapsible `<details>` toggle. They expected each icon to be followed by a visible "what the agent said" line.

**The wrong move (what the agent initially proposed).** Auto-expand the `View content` toggle so the agent's text was visible without clicking. Two reasons that didn't fit the actual problem:

1. The toggle renders the full content (token chips + text pre-block + model reasoning). Auto-expanding 25 of those per report would make the page a wall of `<pre>` blocks, not "an at-a-glance answer."
2. The user's stated symptom was "icons show they ran but no results of what they did" — the rendered HTML actually DID have the agent's result text, but as `text=verdict: not yet complete, more paths needed` rendered inside a flat metadata table mixed with token counts and model reasoning. The text was there, just buried in noise. The bug was presentation, not capture.

**The right move — promote the agent result text into a dedicated visible line.** In `buildPumpStationTurnDetails`, read `event.metadata["contentPreview"]`, strip the `text=` Sprintf prefix that surfaces from upstream `MultimodalContent.toString()`, and emit a dedicated line directly under the event label:

```kotlin
val contentPreview = event.metadata["contentPreview"]?.toString()
val resultLine = if (!contentPreview.isNullOrEmpty()) {
    val stripped = contentPreview.removePrefix("text=")
    "<div class='ps-result-line'><span class='ps-result-label'>Result:</span>" +
        "<span class='ps-result-text'>${escapeHtml(stripped)}</span></div>"
} else ""
```

Render this ABOVE the existing metadata table. The original `contentPreview:` row in the metadata table stays (for canonical completeness — keep the metadata-dump invariant). The "View content" toggle remains for full content browsing.

CSS for the result line:
- `border-left: 3px solid #6366f1` (indigo accent — picks up against the existing palette)
- `background: #f1f5f9` (slightly darker than the panel background so it stands out)
- `font-family: monospace` for the text content (matches the per-turn token summary style)

**Why this matters — and why the failure recurs.** Three trace-visualization failure modes converge here:

1. **Capture-vs-rendering confusion.** A user reports "icons but no results." The first instinct is "the events aren't being captured." They ARE captured (visible in `event.metadata["contentPreview"]`) — the rendering is the problem. Verify the actual rendered HTML before assuming a capture bug.
2. **All-in-one toggle anti-pattern.** The `<details>` toggle pattern works for "show me everything" but not for "show me the headline." Anything that needs at-a-glance scanning must surface a headline line outside the toggle.
3. **Colorblindness / fatigue UX.** When asked "color the input and output so a tired dev can tell at a glance," the right picks are NOT red/green (deuteranopia/protanopia collapse them to the same hue). Teal-cyan `#0e7490` for input + warm-amber `#92400e` for output preserves both luminance difference AND blue-axis distance. Both pass WCAG AA on the pale card background. Black-amber contrast: 4.49:1 (AA-LG at the darker gradient end), so bump amber one shade darker if the gradient dips below that.

**Detection heuristic — when the user says "icons but no results" or "tired and burnt out developer":**

1. Open the rendered HTML. Grep for the agent's known content (e.g. `text=verdict:`) and see if it's in the metadata table but not as a headline.
2. If yes → presentation bug, not capture bug. Promote the contentPreview to a headline line.
3. If the user asked for color differentiation → use teal + amber, not red + green. Verify WCAG AA on the actual card background (compute lum + ratio, don't eyeball).
4. Don't auto-expand toggle-based content as the fix for "I can't see it" — that makes the page denser, not clearer. Promote the headline.

**Companion pitfall — anchor your test assertions on the rendered label, not the bare class name.** The first iteration of `reportPromotesAgentResultTextToVisibleLine` asserted on the literal substring `ps-token-card` (the original class name) and got false-positive PASSes because the CSS selector in the embedded `<style>` block ALSO contained that string. Fix: assert on the rendered `<span class="trace-token-card">` opening tag OR on the visible label text (`TOKEN TOTALS`, `Result:`, etc.), not on the bare class. CSS rules and rendered DOM share the class name.

**Origin:** 2026-07-08 trace-token-totals + agent-result-line session. Plan at `/home/cage/.hermes/plans/trace-token-totals-header.md`. Verification script `hermes-verify-agent-result-line-2026-07-08.py` (forced `--rerun-tasks` + parsed the rendered HTML directly).