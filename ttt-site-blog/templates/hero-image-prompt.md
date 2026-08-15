---
name: hero-image-prompt
description: "Starter prompt template for TPipe blog hero images. Use when the user asks for a hero image prompt, when an article's frontmatter declares an image path that doesn't exist yet, or when drafting any blog post that needs a dark industrial illustration. Captures the 1600x800 banner format, the emerald/signal-red/brass-on-black palette, the left-to-right flow composition, and the alt-text wiring step. Mirrors the established style of reasoning-pipes-explained-hero.png and killswitch-explained-hero.png."
---

# Hero image prompt template (TPipe dark industrial)

Use this when the user asks for a hero image prompt or when an article ships without one. Match the existing family first — three shipped references establish the aesthetic:

- `public/assets/blog/reasoning-pipes-explained-hero.png` — mechanical compiler (gears, punchcards, valves)
- `public/assets/blog/killswitch-explained-hero.png` — emergency cutoff switch (control room, sparks, gauges)
- `public/assets/blog/memory-system-hero.png` — clean architecture diagram (different style — schematic, not illustration; do not duplicate)

The new image should fit between the mechanical illustrations and the schematic. Industrial metaphor, no people, no AI faces, no neon.

## Prompt structure

Replace the bracketed slots with the article's specific subject. Keep the format, palette, composition, and what-to-avoid sections stable — those are what keep the family consistent.

```
HERO IMAGE PROMPT — [article topic]

Format: 1600x800 (3:1 banner, the site crops to 400px height on desktop, 250px on mobile, so keep the focal point in the vertical center)
Style: dark industrial illustration, industrial brutalism, machinist precision, schematic mechanical
Palette: deep matte black background (#0A0A0A), emerald glow for the fluid/data (#10B981 family), signal red on the gate-valve handle and any pressure-warning gauges (#EF4444 family), warm brass and bronze for pipes and fittings, oxidized iron for the structural elements

Composition (left to right):

  - [First element — the entry point, the input]
  - [Second element — the local / working / first-stage mechanism, with internal details visible]
  - [Third element — the gate, valve, or transition (this is the dramatic focal point)]
  - [Fourth element — the global / persistent / second-stage structure, the dominant element, with labeled sub-units]
  - Background depth: more pipes, valve assemblies, and [chambers / gear assemblies / conduits] fading into atmospheric haze behind the main structure. Subtle ambient [emerald / amber] backlight filtering through the gaps
  - Foreground: a brass data plate riveted to the bottom-left corner of the frame, stamped: "[DOMAIN] // [ROLE] // [PROPERTY]"

Mood: deterministic, infrastructure-grade, [era-appropriate historical reference like "the kind of thing a municipal water authority runs in 1932 and never replaces" or "the kind of mechanism a steel mill runs in 1962 and never replaces"]. No people. No fantasy. Real mechanical weight.

What to avoid:
  - No neon. No glow effects beyond the emerald fluid
  - No circuit boards, no server racks, no cloud icons — this is a utility, not a data center
  - No robots, no AI faces, no anthropomorphism
  - No text on the [bottles / chambers / machinery body] other than the brass [pressure ratings / nameplates]
  - No cartoon style, no isometric game-art, no 3D render
  - Do not duplicate the existing [style family member]. This is an illustration of the [specific metaphor], not a copy

Reference images in same family already shipped:
  - /public/assets/blog/reasoning-pipes-explained-hero.png — [what it shows]
  - /public/assets/blog/killswitch-explained-hero.png — [what it shows]
  - /public/assets/blog/memory-system-hero.png — clean architecture diagram (different style)
```

## Worked example: ContextWindow and ContextBank

The actual prompt I shipped for the ContextWindow/ContextBank article. This is the canonical reference for the "two-tier memory utility" metaphor.

```
HERO IMAGE PROMPT — ContextWindow and ContextBank

Format: 1600x800 (3:1 banner, the site crops to 400px height on desktop, 250px on mobile, so keep the focal point in the vertical center)
Style: dark industrial illustration, industrial brutalism, machinist precision, schematic mechanical
Palette: deep matte black background (#0A0A0A), emerald glow for the fluid/data (#10B981 family), signal red on the gate-valve handle and any pressure-warning gauges (#EF4444 family), warm brass and bronze for pipes and fittings, oxidized iron for the structural elements

Composition (left to right):

  - A heavy brass inlet pipe enters from the far left at a 30-degree downward angle, carrying a slow current of emerald-glowing fluid (the user prompt + system context arriving at the pipe)
  - The pipe feeds into a small, cast-iron cylindrical reservoir mounted on riveted steel brackets — the ContextWindow. The reservoir is glass-fronted (or has a porthole window) so the contents are visible. Inside: a small rack holding 4-6 weighted glass bottles of varying sizes and shapes (the lorebook entries). The bottles have brass caps with pressure ratings stamped on them (the weights). The fluid level inside the reservoir is visible and the bottles are partially submerged
  - A second glass-fronted chamber is attached to the right side of the reservoir holding a small stack of paper notes and short ribbon strips (the contextElements and converseHistory slots)
  - A brass outlet pipe exits the bottom-right of the reservoir, drops down, and runs along the bottom of the frame to the right
  - The pipe runs past a massive mechanical gate-valve — the mutex. The valve body is cast iron with brass bolts around the flange, a heavy spoked hand-wheel on top (currently in the OPEN position), and signal red paint on the wheel rim. A small mechanical counter on the side shows "000000" — the token accumulator
  - The pipe then rises up and connects into the right side of a massive municipal-scale water main structure — the ContextBank. This is the dominant element: a wall of cast iron with multiple labeled pressure chambers (rectangular panels with brass nameplates), one chamber per page key. Visible labels in machined sans-serif: "story", "session", "campaign_facts", "user_profile", "world_rules". The chambers each have a glass inspection window showing fluid levels at different heights (different windows have different amounts of data). Brass pressure gauges on top of each chamber
  - Background depth: more pipes, valve assemblies, and pressure chambers fading into atmospheric haze behind the main structure. Subtle ambient emerald backlight filtering through the gaps
  - Foreground: a brass data plate riveted to the bottom-left corner of the frame, stamped: "CONTEXTBANK // PERSISTENT MEMORY // THREAD-SAFE"

Mood: deterministic, infrastructure-grade, the kind of thing a municipal water authority runs in 1932 and never replaces. No people. No fantasy. Real mechanical weight.

What to avoid:
  - No neon. No glow effects beyond the emerald fluid
  - No circuit boards, no server racks, no cloud icons — this is a utility, not a data center
  - No robots, no AI faces, no anthropomorphism
  - No text on the bottles or reservoir body other than the brass pressure ratings
  - No cartoon style, no isometric game-art, no 3D render
  - Do not duplicate the memory-system-hero (which is a clean architecture diagram). This is an illustration of the metaphor

Reference images in same family already shipped:
  - /public/assets/blog/reasoning-pipes-explained-hero.png — mechanical compiler with gears
  - /public/assets/blog/killswitch-explained-hero.png — emergency cutoff switch
  - /public/assets/blog/memory-system-hero.png — clean architecture diagram (different style)
```

## After the image lands: alt-text wiring is required

The site does NOT use the filename as a key into a registry. `src/components/blog/BlogPost.astro` has a chained ternary that returns a specific alt text per known filename and falls back to a generic one for anything else. The fallback is wrong for every shipped post.

When you write the prompt, also patch the ternary:

1. Open `src/components/blog/BlogPost.astro`
2. Find the nested ternary that starts with `image.includes('memory-system-hero')`
3. Add a new branch for the new filename BEFORE the final fallback
4. Write a 50-80 word descriptive alt: subject, layout, color palette, mood, the specific elements (bottles / chambers / gauges / etc.). Not generic.
5. Verify the file: `curl -sS http://127.0.0.1:4321/blog/<slug>/ | grep 'alt='` and confirm the new alt renders

If the vision tool can't read the existing reference images (oversized, 413 from the analyzer), write the alt text against the prompt's described content, not against a placeholder. The prompt description IS the source of truth for the alt text when you can't run the image through the vision model.

## When the user provides a generated image instead of asking for a prompt

Workflow:

1. Move the file from `~/Downloads/<name>.png` to `public/assets/blog/<slug>-hero.png` (rename to match the frontmatter `image:` path)
2. Patch the alt-text ternary as above
3. Verify the build: `curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:4321/blog/<slug>/` should return 200
4. Visually verify in the browser if you have vision access; otherwise trust the prompt-derived alt text
