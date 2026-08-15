# External Game Survey — Premise Wording Grounding

**Purpose:** Canonical methodology for surveying landing pages of direct PvP board games, AI-driven narrative games, and roguelike / possibility-driven games before recommending an Autogenesis premise sentence. Internal paraphrase of the operator's interview produces variants that are technically true but commercially weak. External grounding — lifting the actual wording patterns that move product — is mandatory.

**Origin:** Operator's correction, 2026-08-09 — *"Why don't we conceptually go find a bunch of landing pages for pvp games and similar game concepts and see what those look like. Learn the wording more."*

## When to use

- Drafting or recommending a final premise sentence for the Autogenesis landing page hero.
- Auditing an existing premise draft against external copy patterns.
- Re-grounding a premise after operator feedback ("it doesn't really sell the concept as strong as it could be").

## The three-promise standard (what every survey must check)

For each landing page surveyed, score against the three load-bearing promises of Autogenesis:

1. **You can attempt ANY action** — copy must convey infinite player agency, not a menu.
2. **The rules still apply and somehow it just works** — copy must anchor that the world responds in rule-bound ways, not vibes.
3. **It feels like a real game** — copy must name scoring, win conditions, factions, or other rule-bound consequences. Loop-only copy that omits this collapses into the "AI writes funny stories" failure mode.

A premise that satisfies 1+2 but elides 3 was the rejection cause for Variant 1 (2026-08-09). Any survey finding that lifts a "loop-only" pattern must be flagged for the missing third leg.

## Three research threads

### Thread 01 — Direct PvP board games
Target 10-15 sources across: Twilight Imperium, Root, Gloomhaven / Frosthaven, Catan (digital), Wingspan, Scythe, Dune Imperium, Terraforming Mars, Brass Birmingham, Spirit Island, Blood Rage, Ark Nova, plus 2-3 independently discovered strong examples.

Per-source extraction rubric:
1. Premise sentence / hero sub-headline (verbatim).
2. Loop statement (3-beat phrasing if present).
3. The "feels like a game" tell (verbatim, explicit win conditions / scoring / faction asymmetry).
4. Section order above and below the fold.
5. Hero media + beat it shows.
6. CTA pairing + promise each makes.
7. Hedge audit (verbatim soft superlatives + frequency).
8. What makes this page trustworthy to a board-game skeptic.

### Thread 02 — AI-driven narrative games
Target 10-15 sources across: Hidden Door, Inworld AI, Latitude / AI Dungeon (**anti-pattern only — capture what's WRONG with their pitch, not what's right**), Charisma.ai, Spiritfarer, Hades, Disco Elysium, Citizen Sleeper, Pentiment, Norco, Wildermyth, Caves of Qud, Dwarf Fortress, RimWorld.

Per-source extraction rubric: same as Thread 01, plus an explicit pass at:
4b. **How they sell "anything can happen" WITHOUT losing the rule-bound feel** — quote the exact wording. This is the critical pattern Autogenesis must solve.
9. AI Dungeon comparison: what Latitude's landing page gets wrong; what Autogenesis must NOT copy.

Hades and Disco Elysium are gold standards because they sell infinite narrative possibility inside rule-bound systems — exactly the Autogenesis pitch challenge.

### Thread 03 — Roguelikes / possibility-driven / "build your own X" games
Target 10-15 sources across: Balatro, Slay the Spire, Hades II, Inscryption, Dicey Dungeons, FTL, Cultist Simulator, Monster Train, Spelunky, Noita, Crypt of the NecroDancer, Vampire Survivors, Dead Cells, Streets of Rogue.

This thread's primary deliverable is the verbatim **"build your own X" pattern catalog** — quotes of "build your own deck," "build your own run," "craft your strategy," "every choice matters," etc. across all sources. This pattern is the strongest candidate for Autogenesis's "invent your own action" framing.

Balatro is the gold standard for "endless replayability" pitch — dissect its wording carefully.

## Findings file naming convention

Three threads produce three findings files at:
- `~/Desktop/Workspaces/md/autogenesis-landing-research/01-pvp-board-games-findings.md`
- `~/Desktop/Workspaces/md/autogenesis-landing-research/02-ai-narrative-games-findings.md`
- `~/Desktop/Workspaces/md/autogenesis-landing-research/03-possibility-games-findings.md`

Plus a steering file at:
- `~/Desktop/Workspaces/md/00-autogenesis-landing-research-steering.md`

And a synthesis report at:
- `~/Desktop/Workspaces/md/autogenesis-landing-research/FINAL-report-external-game-survey.md`

## Synthesis gate (before recommending any final premise sentence)

The agent MUST NOT promote a premise sentence to "final" until:

1. All three thread findings files exist with >10 sources each.
2. The "build your own X" catalog (Thread 03) contains verbatim quotes from at least 6 sources.
3. The synthesis report identifies 3+ cross-category patterns (patterns that appear in two or more of the three threads).
4. Each candidate premise sentence is scored against the three-promise standard above.
5. Each candidate is audited against the banned hedge phrases from `references/anti-premise-failure-modes.md` + the Autogenesis marketing voice ban list (`honest assessment`, `reasonable choice`, `well-suited`, `well-architected`, `vibrant community`, `extensive documentation`, `an architectural ceiling`, `Not sure which comparison to read first`, `stay with LangGraph`, `it could be argued`, `perhaps`).

If any check fails, the premise is "draft, not final," regardless of how good it reads internally.

## Per-thread output format

Each thread's findings file follows:

```markdown
# [Category] Landing Pages — Premise & Pitch Patterns

## Sources Surveyed
[Numbered list with URLs]

## Per-Source Findings
[For each: premise sentence, loop statement, "feels like a game" anchor, anything-can-happen balance wording, section order, hero media, CTA pair, hedge audit]

## Synthesis
[200-400 word summary. Address: how does this category sell (a) any-action-can-be-attempted + (b) rule-bound consequence + (c) feels-like-a-game as a single triple-promise unit.]

## Patterns to Borrow
[3-5 specific wording moves that work]

## Patterns to Avoid
[3-5 specific wording moves that flatten the premise]

## Thread 03 only — The "Build Your Own X" Pattern Catalog
[Verbatim quotes across all sources]
```

## Pitfalls

- **DO NOT skip Thread 02's anti-pattern analysis.** AI Dunson's pitch collapses the game into "AI writes funny stories" because it leads with infinite possibility without the rule-bound anchor. Capture the specific failure mode so the Autogenesis copy doesn't repeat it.
- **DO NOT paraphrase landing-page copy.** Quote verbatim. Paraphrase loses the inflection.
- **DO NOT survey print-game pages preferentially.** Digital adaptations (Tabletop Simulator, Board Game Arena, official digital releases) have more developed hero copy.
- **DO NOT recommend a premise sentence based on internal paraphrase alone.** The whole point of this methodology is external grounding.
- **DO NOT collapse the three threads into one cross-category summary without first scoring each candidate premise against the three-promise standard.** A premise that satisfies 1+2 but elides 3 fails.

## Cross-references

- `references/premise-sentence-catalog.md` — operator's verbatim interview quotes + the four canonical loop variants. The internal-paraphrase baseline that this methodology is meant to escape.
- `references/anti-premise-failure-modes.md` — the collapse modes this survey is structured to defend against.
- `autogenesis-game-mechanics` — for the rule-bound consequence claims (territory counts, scoring, 51/55/60% victory thresholds, 25-round cap, karma/nemesis system) that promise 3 must anchor against.
- `creative:humanize` — for the post-draft humanizer pass on any premise sentence this methodology produces.