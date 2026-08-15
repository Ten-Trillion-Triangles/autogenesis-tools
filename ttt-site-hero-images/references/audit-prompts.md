# Hero image audit prompts

Paste-ready vision_analyze prompts for each visual family. Use after generating any hero image, before deciding to ship.

## Pipe schematic family audit

```
Audit this hero image for a tech blog post on [POST TOPIC]. Check: (1) is it dark navy + steel teal palette like a municipal/industrial schematic? (2) Does it use pipes/industrial metaphor suitable for [POST TOPIC]? (3) Is the composition widescreen banner, 16:9? (4) Any obvious flaws: garbled text, people, neon, circuit boards, illegible labels? (5) Is it usable as a hero? Be brutally honest — if it's bad, say so. Score C+ usable but generic separately from "post-specific metaphor signal."
```

The score breakdown in (5) is the load-bearing question. C+ usable means palette + composition match, but the metaphor could illustrate water utilities or DevOps pipelines — anything. Post-specific signal means a reader glancing at it would register the topic. The audit must surface this distinction before the wire-up decision.

## Comparison diagram family audit

```
Audit this comparison-diagram hero for a tech blog post comparing [PRODUCT] against [COMPETITORS]. Check: (1) is it dark dot-grid background with neon accents? (2) Hub-and-spoke composition with protagonist at center? (3) Named competitors visible? (4) Punchy declarative tagline at the bottom? (5) Any garbled labels, illegible product names, or AEO/SEO-breaking issues? Be brutally honest — if a competitor name is rendered wrong, say so.
```

## Universal audit (run regardless of family)

```
Audit this hero image for a blog post. Check: (1) aspect ratio widescreen 16:9? (2) composition leaves room for headline overlay (negative space top-left or top-center)? (3) reads at thumbnail size (would a 200px-wide preview still convey the metaphor)? (4) no AI artifacts: melted geometry, smeared text, uncanny elements, distorted faces? (5) brand-aligned (no emoji, no neon pinks/purples unless intentional, no clip-art)? Score A/B/C/D for ship-readiness.
```

A = ship now. B = ship after one regen with specific hook. C = ship with caveat, surface the generic-ness to user. D = do not ship.

## Audit output format

Always surface the verdict to the user with three concrete paths:

1. **Ship** — C+ generic but on-family. Wire it up.
2. **Regenerate v2** — same prompt + post-specific hook. Costs one more image credit.
3. **Reuse existing hero** — point at which shipped hero fits. Saves time and credits.

Never silently ship a C+ without flagging the score. The `image-prompt-craft` skill's audit-and-iterate workflow covers the prompt side; this file covers the visual side.