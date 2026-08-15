# Hero image prompt template (pipe-schematic family)

Paste-ready skeleton. Fill in the bracketed placeholders, remove the brackets, ship the single block. No preamble, no postamble, no "What to avoid" section. Anti-instructions inline with the rest.

## The template

```
Wide horizontal 16:9 banner in the dark industrial style of a [SCHEMATIC TYPE: municipal engineering blueprint / substation control schematic / mechanical pumping station cross-section]: [PALETTE: deep matte navy background (#0B1A2A) with soft radial vignette], foreground composed entirely of [METAPHOR: flat two-tone shaded cast-iron pipes / chrome gauges / municipal apparatus] tracing [FLOW DIRECTION: an interconnected network entering from the lower-left and exiting upper-right / a left-to-right flow with measurement checkpoints], with [COMPOSITION DETAIL: uniform pipe diameters, rounded 90-degree elbows only, smooth quarter-circle bends, generous negative space top and bottom], [ACCENT: small white triangular arrowheads threading through the pipe interior showing flow direction / tiny white and pale-gray circular nodes at junctions / one prominent brass-toned gauge instrument in the foreground with a chrome needle], no people, no circuit boards, no robots, no fantasy, no neon, no legible technical text, the mood calm and infrastructure-grade like a 1932 [WATER AUTHORITY / SUBSTATION / PUMP STATION] schematic that was never replaced.
```

## Fill-in examples by post topic

### JVM-native production runtime post

```
Wide horizontal 16:9 banner in the dark industrial style of a municipal engineering blueprint: deep matte navy background (#0B1A2A) with a soft radial vignette, foreground composed entirely of flat two-tone shaded cast-iron pipes (steel teal #4A8AA0 lighter face, deep slate teal #2E5A6E underside, no gradients, no textures) tracing an interconnected network that enters from the lower-left and exits upper-right, pipe diameters uniform throughout, rounded 90-degree elbows only, all bends smooth quarter-circles, pipes arranged so the network subtly spells the word JVM as a hidden letterform visible on close inspection without any actual text rendered, small white triangular arrowheads (#F2F5F7) threading through the pipe interior showing flow direction left to right, tiny white and pale-gray circular nodes at T-intersections, junctions, and along pipe runs acting as monitoring/valve points, one prominent brass-toned gauge instrument in the upper-right foreground with a chrome needle pointing into the green band suggesting cold-start timing, generous negative space top and bottom, no people, no circuit boards, no robots, no fantasy, no neon, no legible technical text, the mood calm and infrastructure-grade like a 1932 water authority schematic that was never replaced.
```

### Memory-bank comparison post

Use the comparison-diagram family template instead. The pipe family is wrong for comparison pages — see `references/audit-prompts.md` for the comparison family audit.

### Substrate / framework post

```
Wide horizontal 16:9 banner in the dark industrial style of a mechanical pumping station cross-section: deep matte navy background (#0B1A2A) with soft radial vignette, foreground composed of flat two-tone cast-iron apparatus (steel teal #4A8AA0 lighter face, deep slate teal #2E5A6E underside) showing a precision-machined substrate plate with bolt-down mounting points, weighted pressure vessels stacked at varying heights, chrome dials on each vessel face showing different gauge readings, copper-bronze pipe runs connecting the vessels through bolted flanges, a single bright emerald glow (#10B981) emanating from a maintenance hatch in the lower-left foreground suggesting the operating substrate beneath, no people, no circuit boards, no robots, no fantasy, no neon, no legible text labels on the dials, the mood industrial-brutalist and machinist-precise, the kind of apparatus a municipal water authority ran in 1932 and never replaced.
```

## Negative-instruction pattern (inline)

The negative instructions (`no people, no circuit boards, no robots, no fantasy, no neon, no legible technical text`) belong **inside** the prompt, not in a separate "What to avoid" section. The `image-prompt-craft` skill is explicit on this — image models weight in-prompt negatives differently from a separate "What to avoid:" block.

## When to add a post-specific hook

A pipe-family prompt without a post-specific anchor produces C+ generic. Common anchors that tie the metaphor to the post topic without text labels:

- A **brass gauge instrument with a chrome needle** in the foreground → suggests measurement/control (cold-start timing, token budget, throughput)
- A **weighted glass bottle in amber fluid** → suggests reservoir/memory (ContextBank pages)
- A **red-painted gate-valve wheel** → suggests kill switch / termination (KillSwitch posts)
- **Pipes spelling a hidden letterform** → "subtly spells X" without rendering text; only works for 3-4 character words (JVM, OK)
- **A maintenance hatch with emerald glow** → substrate/runner visible underneath

Pick one anchor per post. Don't combine — the model gets confused and renders none of them.

## Length guideline

A good pipe-family prompt runs 250-450 words. Below 200 produces generic. Above 500 produces over-spec'd outputs that ignore half the constraints. The JVM example above is ~280 words and shipped cleanly.