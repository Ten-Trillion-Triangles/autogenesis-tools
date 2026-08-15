# Demo Asset Mapping

Canonical demo asset set at `/home/cage/Desktop/Workspaces/ttt-site/public/gifs-final/`. Verified dimensions: 1280×652, 15fps for GIFs / 60fps for MP4+WebM, 8–12s per clip.

## Asset Inventory (verified 2026-08-03 via ffprobe)

| File | Duration | GIF size | MP4 size | WebM size | Beat |
|---|---|---|---|---|---|
| `01-map-typing.{gif,mp4,webm}` | 8.0s | 2.4 MB | 345 KB | 530 KB | Player input |
| `02-agent-stream.{gif,mp4,webm}` | 10.0s | 4.3 MB | 751 KB | 962 KB | Execution stream |
| `03-agent-planning.{gif,mp4,webm}` | 10.0s | 1.4 MB | 193 KB | 278 KB | Plan/validate |
| `04-narrative-reveal.{gif,mp4,webm}` | 12.0s | 2.9 MB | 382 KB | 664 KB | Story output |
| `06-world-update.{gif,mp4,webm}` | 10.0s | 2.4 MB | 581 KB | 733 KB | World-state change |

Total bundle: ~17 MB if every format ships; ~2.5 MB if MP4-only ships; ~3.2 MB if WebM-only ships.

Note: there is no `05` in the canonical set. The five clips above are the loop. Numbering gap is intentional in the source layout, not a missing file.

## Beat-by-Beat Read

Each clip is a single 8–12 second beat of the turn loop. The loop is: **type → stream → plan → reveal → update**. The clips are sequenced in this order on disk.

### 01-map-typing (Player Input)
- **What you see:** A dark blue world map with red-tile clusters and circular numbered units. The bottom-left input field shows typed text: `Lord Maple Tree deploys two major invasions to expand his empire. To the west into @Great White North he sends his general: General Moustache to deploy the ent army's syurpy might to defeat President Tuna Fish and subjugate the land. To the east, He personally leads the ent army in the conquest of @Greenland`.
- **Implication:** Player types a freeform action. The map is the visible consequence surface. The command character counter ticks up (169/500).
- **Hero use:** YES — first clip. Establishes player agency.

### 02-agent-stream (Execution Stream)
- **What you see:** A panel titled `Streaming - Agent Work Stream` scrolls JSON upward rapidly. Contains `description`, `CharacterRationale`, rule definitions like `AntiMundanityProtocols` and `PointingInCohesion`.
- **Implication:** The system is processing. The reader who reads this clip carefully sees that rules and structure are being applied — not vibes.
- **Hero use:** NO as the focal point. Scares engineers and bores everyone else. Use as background b-roll behind the typed-action panel, or skip in the first-scroll reel.

### 03-agent-planning (Plan + Validate)
- **What you see:** `Agent Planning...` with a spinning gear icon, subtext `Analyzing world state and formulating strategy.` A pill rail appears below: `Start → Action → Planning → Writing → Judging → Dispatch → NPCs → World → Counter`. The `Planning` step is highlighted.
- **Implication:** The game is using a real pipeline. The reader who stops on this frame sees that the AI isn't making a single prompt call — it's a multi-step process.
- **Hero use:** YES as a b-roll interstitial between `01` and `04`. The pill rail is the strongest visual proof of "this is a real game with rules, not ChatGPT-with-a-prompt."

### 04-narrative-reveal (Story Output)
- **What you see:** Generated prose fills the central narrative panel character-by-character. The Game History panel on the left already shows `Turn 1 - Lord Maple Tree` with the player action. The status text below reads `Generating narrative...`. The story is `{ "newChapter": "Deep the within vacuolar tissues of Maple Tree Lord, a civil war of microscopic proportions raged, mirroring the carnage of the surface world...`.
- **Implication:** The world is now writing the player's action into prose. The story is absurd (vascular tissue inside a tree god) — that's the hook.
- **Hero use:** YES — second clip. The character-by-character typing effect is visually distinctive; shows the AI narrating in real time.

### 06-world-update (World-State Change)
- **What you see:** `Updating World State...` with a spinning globe icon, subtext `Applying global changes and territory shifts.` Below the icon: a row of small location pills (`Kabul`, `Tunisia`, `United States`, etc.).
- **Implication:** The narrative is becoming mechanical state. The board is being changed.
- **Hero use:** YES — third/closing clip. Establishes that the story produces real board changes.

## Hero Composition Recommendation

Three-clip reel, 30s total:

1. `01-map-typing` (8s) — player agency, action in motion
2. `04-narrative-reveal` (12s) — story output, character-by-character typing
3. `06-world-update` (10s) — board change, world state resolving

Optional 5-clip full loop, 50s total: insert `02-agent-stream` and `03-agent-planning` between beats 1 and 2 as proof that the AI work is structured.

## Anti-Patterns for Asset Use

- **Do NOT lead with `02-agent-stream` as the hero focal point.** Engineers stop scrolling to read the JSON; non-engineers scroll past. The stream is evidence for the curious, not the hook for everyone.
- **Do NOT use a static screenshot of the top bar (Main Score / Military / Diplomatic / Research / Summit) as the hero.** Numbers without a story do not communicate "you can do anything."
- **Do NOT autoplay a single GIF that loops the typing input forever.** The user sees one beat and loses the loop. The loop requires the resolve beats to land.
- **Do NOT crop the resource score digits or the world map tiles to fit a smaller hero. They are the proof that this is a board game, not a chatbot.**
- **Do NOT use MP4-only.** Some embeds (email clients, Slack previews, certain CMS contexts) only support GIF. Ship all three formats and let the browser pick.

## Implementation Note

The HTML markup pattern from `media/video-highlight-extraction` is the canonical embed. The `<video>` element with WebM → MP4 → GIF fallback chain (in that source order) is the recommended shape; the GIF fallback only loads if the browser refuses both video formats.
