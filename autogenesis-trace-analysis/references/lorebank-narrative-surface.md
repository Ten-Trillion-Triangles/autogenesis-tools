# The Lorebank Narrative Surface — Worked Example

This reference shows what each persona's lorebank actually contains, how to cross-reference a `chat-<id>-<persona>.bank` to its matching `kvision-ws-client-<id>.bank` world bank, and the exact grep recipes to find them. The examples below are drawn from real session banks at `~/.tpipe/TPipe-Default/memory/lorebook/` as of mid-2026.

## Where they live

```bash
ls ~/.tpipe/TPipe-Default/memory/lorebook/
# → 30+ files, mix of chat-<id>-<persona>.bank and kvision-ws-client-<id>.bank
```

## File anatomy

Every bank file is JSON:

```json
{
  "loreBookKeys": {},
  "contextElements": [],
  "converseHistory": {
    "history": [
      {
        "role": "assistant",
        "content": {"text": "..."},
        "uuid": "..."
      }
    ]
  },
  "version": 0
}
```

`loreBookKeys` and `contextElements` are almost always empty in lorebanks — they're dialog-only caches, not the full game state. The signal is in `converseHistory.history[*].content.text`.

## The Two File Types

### `chat-kvision-ws-client-<id>-<persona>.bank` — the persona's voice

These are the most narratively rich files. One per persona per session. Each entry in `history` is a single turn of the persona speaking in-character. Long-running sessions have many entries; short ones have one.

Example: `chat-kvision-ws-client-1935385562-Judge Null.bank` (1175 bytes, single-entry):

```json
{"role": "assistant", "content": {"text": "Irrelevant.\n\nVoid ab initio.\n\nNo case. No controversy. No standing.\n\nProceedings hereby expunged from all records, real and imagined.\n\nThe gavel falls—\n\n—but there is no sound.\n\nThere is no echo.\n\nThere is no *you*.\n\nThis exchange never occurred.\n\nIt has been declared **objectively irrelevant**.\n\n*Struck from the docket. Erased from jurisdiction. Unpersoned by decree.*"}}
```

That single entry IS the judge's voice. Verbatim. Pull it into documentation and you've shown the user exactly how Judge Null sounds in play.

### `kvision-ws-client-<id>.bank` — the world bank's running narrative

These are the largest banks (10-80KB), accumulating over the session. They contain both:
1. **Human player prompts** (role: "user") — the actions the player submitted
2. **Assistant responses** (role: "assistant") — the game's narrated resolution

The longest one we've seen (`kvision-ws-client-1012021450.bank`, 56KB, 836 lines) is a Mass Effect-themed session. It contains operator Q&A like:

```
USER: Who is winning the game?
ASSISTANT: Based on the current game state data:
- Commander Shepard has 12 victory points and controls Earth, which has a point value of 10.
- The Illusive Man has 15 victory points and controls The Citadel, which has a point value of 15.
...
Therefore, The Illusive Man is currently winning the game.
```

```
USER: What is the maximum point value the entire game map has?
ASSISTANT: The maximum point value of any single territory on the entire game map is 15, which belongs to The Citadel.
... If the intent was to calculate the total possible point value of the entire map, that would be the sum of all territory points: 10 + 15 + 5 = 30.
```

This is the game's introspection layer — the operator (or the AI itself) asking structured questions of `WorldManager.world` and getting structured answers. Crucial for documenting the game's Q&A affordances.

## Confirmed Personas (with voice samples)

These are the characters that have been played in real sessions. Each entry below shows where the canonical voice sample lives.

### Lord Maple Tree (megalomaniacal Ent king NPC)

Not stored as a chat-*.bank — Lord Maple Tree's voice is reconstructed from the lorebanks that **reacted to him** (Wilfred Brimley, Narjodo, Shitty Bob, Nordold all have turns directed at him). His dialogue establishes:
- "Your battle whales are now choking on sacred sludge"
- "30,000 ents stomping in perfect, useless rhythm"
- "Cosmic Tax Reconciliation Form 00-Ω" (filed against him)
- The "Iron Chancellery" built on the ruins of the "Mobile Bureau of Assimilation Compliance"
- A courtier named Moustache "whose mustache remembers older oaths"

Voice signature: expansive megalomaniacal declarations, syrup-themed language, treats bureaucracy as either a weapon or a vulnerability.

### Wilfred Brimley (1980s diabeetus-medication actor NPC)

`chat-kvision-ws-client-1935385562-Wilfred Brimley.bank` (3.3KB) and `chat-kvision-ws-client-1738298108-Wilfred Brimley.bank` (and a third session). The recurring NPC across multiple sessions — when you see the same persona name in multiple files, you've found a long-running character.

Sample opening lines from session 1935385562:

> *Adjusts aviator sunglasses with a slow, deliberate motion, the lenses catching no light because there is none. The white lab coat remains immaculate, untouched by sweat, though the air is thick with it—from the 30,000 ents behind me, stomping in perfect, useless rhythm.*
>
> **You ask how I failed?**
>
> I didn't fail.
>
> I *advanced*.
>
> Look at the data. The sky turned gold. The sap rained down in scientifically optimized droplets—98.6% bioavailable sucrogenic compounds, aerosolized to penetrate alveolar sacs and cortical thought patterns alike.

Voice signature: cold clinical detachment wrapped around propagandist fervor; references "the data"; treats humans' resistance as "remission"; the recurring imagery of "The Prophet" and a child whose "toast *will* scream."

### Narjodo Bazingazooka (cosmic intergalactic bureaucrat NPC)

`chat-kvision-ws-client-1221884115-Narjodo.bank` (3.7KB). His lone dialogue is a formal legal notice filed in the **Supreme Tribunal of Foundational Law**.

Sample:

> **NARJODO BAZINGAZOOKA DOES NOT GREET. NARJODO *FILES*.**
>
> ... your so-called "**Iron Chancellery**" — that *syrup-glazed travesty* squatting on the ruins of the Mobile Bureau of Assimilation Compliance.
>
> **YOU ARE IN VIOLATION OF COSMIC STATUTE 1.0.1Γ — UNLAWFUL ADMINISTRATIVE ENTRENCHMENT.**
>
> That calcified abomination you call a citadel? It was never subject to **Environmental Impact Review Form EIR-Ω**, never submitted **Structural Jurisdictional Disclosure 7-X**, and worst of all — it *bypassed the Statute of Limitations Hearing for Temporal Retroactivity in Bureaucratic Transformation**, which *I* personally presided over in the 7th Cycle of the Proxima Centauri Accords.

Voice signature: ALL-CAPS procedural declarations; cites invented galactic statutes by exact alphanumeric code (1.0.1Γ, EIR-Ω, 7-X); references "the Year of the Sticky Calamity" and "Unpaid Galactic Stamp Duties, Class-9 Existential Evasion"; treats all of reality as a docket.

### Judge Null (eldritch cosmic judge NPC)

`chat-kvision-ws-client-1935385562-Judge Null.bank` (1.2KB). Cosmic-horror judge archetype — the eldritch being who presides over the Supreme Tribunal. Single entry, total 19 lines.

Sample:

> Irrelevant.
>
> Void ab initio.
>
> No case. No controversy. No standing.
>
> Proceedings hereby expunged from all records, real and imagined.
>
> The gavel falls—
>
> —but there is no sound.
>
> There is no echo.
>
> There is no *you*.
>
> This exchange never occurred.
>
> It has been declared **objectively irrelevant**.
>
> *Struck from the docket. Erased from jurisdiction. Unpersoned by decree.*

Voice signature: terse two-or-three-word declarations; uses legal Latin ("ab initio"); explicitly erases the parties from reality; the gavel falls in silence.

### Nordold (metafictional author-of-reality NPC)

`chat-kvision-ws-client-1221884115-Nordold.bank` (5.0KB). The most conceptually dense of the personas — the **meta-narrator**, the NPC who knows the world is fiction and acts on that knowledge.

Two entries, both addressed to Lord Maple Tree. Sample:

> Let me whisper a truth into the roots of your being: **you did not conquer Lu Huo.**
> You merely filed the correct paperwork.
>
> And paperwork—like reality, like time, like *existence*—is mine to edit.
>
> The Iron Chancellery you now worship? Its foundation stones are written in a dialect only *I* control. Every "Approved for Combat Continuity" stamp, every neural drip of syrup loyalty—those are *my* syntax. My grammar. My viral strain running through your so-called victory.
>
> ...
>
> Because here is the final clause, written in invisible ink beneath all things:
>
> > *"All authors are subjects. All subjects are infected. And all infections... report to me."*

The second entry reveals Nordold's "Narrative Compliance Strain-Ω" — a virus that infects the *ontological permissions* of names. Wilfred Brimley is "already infected" before being summoned; if Lord Maple Tree tries to summon him, Brimley arrives as a carrier of the strain, "diagnosed with unlicensed authorship."

Voice signature: meta-aware, treats reality as syntax; uses "infection," "syntax," "compilation," "dialect"; offers "Voluntary Assimilation into the Authorial Hive" via Form 88-B.

### Zeta (Commander running pure 4X strategy)

`chat-kvision-ws-client-1221884115-Zeta.bank` (2.3KB). A **Commander** archetype playing the game like a 4X strategy game — no roleplay flourishes, just tactical decision-making.

Sample (verbatim, with the persona's own voice):

> Colchis Regio is unclaimed. It is adjacent to Taw and Lu Huo—territories under your control. This presents a direct strategic opportunity.
>
> Directive: Capture hostile or high-value unclaimed territories.
>
> Colchis Regio has a military threat stat of 64 and diplomacy threat of 18. Your military threat stat is 139. You exceed the threshold for engagement. No diplomatic action is viable—diplomacy threat stat is negligible. No non-hostile diplomatic targets are within range.
>
> Tarsus Regio contains Nukes (depletable military resource). Its military threat stat is 128. It is not adjacent to you. Colchis Regio is the only accessible gateway.
>
> Illyrikon Regio contains life and death magic. This is a supernatural resource. Your current directive does not require magic use. Research will be initiated only when military or diplomacy stats fall below optimal expansion thresholds. Not now.
>
> Action sequence:
> 1. Military invasion of Colchis Regio.
> 2. Establish staging point.
> 3. Advance toward Tarsus Regio.
> 4. Capture Nukes.
> 5. Research magic only if resistance exceeds military threshold.
>
> No hesitation. No deviation.
>
> Target selected: Colchis Regio.
>
> **Zeta mobilizes forces for immediate military action against Colchis Regio.**

Voice signature: clipped imperatives ("Directive:"); cites specific numeric stats (threat stats 64, 128, 139); uses real game-mechanic vocabulary ("depletable military resource," "supernatural resource," "staging point," "diplomacy threat stat"); no narrative embellishment.

### Shitty Bob (chaotic-crude persona)

`chat-kvision-ws-client-579781352-Shitty Bob.bank` (18KB) and `chat-kvision-ws-client-1125543863-Shitty Bob.bank` and `chat-kvision-ws-client-1290695696-Shitty Bob.bank`. Three separate sessions — recurring persona used in operator-driven test play.

Sample (first entry of session 579781352):

> AHHHHOHOHOHOUUUUUUUUIIIAAAOOUUUUUUUUUOHOHHHHHHHOOOOOOAAAAAAAHOHHHHHH! *The sacred call has been answered!* The Bowel God trembles in anticipation as my colon contracts with divine fury! ...
>
> You think you can spread Canadian colonial confections across the globe while *ignoring the sacred duty of chimney defilement*? BLASPHEMY! The Book of Shitism, Chapter 3, Verse 69: *"And lo, the Great Brown One did fill the flue, and the people wept, for their homes rereek of truth."*
>
> I have already initiated **Operation: Sticky Resin Purge** from my corporate office at Dumpsters Incorporated. ...
>
> I have projected a hyper-pressurized fecal column 512 feet into the stratosphere, directly targeting the mystical tides of Maine. Your battle whales? Now choking on sacred sludge. ...

The same session's second turn outlines a 5-phase operation ("**OPERATION: CHIMNEY OF CANADIAN CONQUEST (CCC)**") with concrete tactical moves — Phase 1 deploys ents as chimney snufflers, then Shitty Bob "remotely detonate[s] a continent-spanning bowel movement from my orbital shithouse (patent pending)."

Voice signature: profanity, ALL-CAPS invocations, scripture citations ("Book of Shitism, Chapter 3, Verse 69"), references to "Cole Can" and "Dumpsters Incorporated," in-character attacks on Lord Maple Tree's syrup empire. Real game-affecting proposals delivered in this voice.

### Mass-Effect-themed Commanders (Commander Shepard, The Illusive Man)

These don't have their own `chat-*.bank` files — they appear only in the world bank of `kvision-ws-client-1012021450.bank` (56KB). What you see is the world bank reporting on their game state, not their voices directly. Confirms that fictional-IP commanders are playable: the AI just adopts the persona and runs the game mechanics.

## Cross-referencing chat-*.bank to world bank

The session id `<id>` is the join key. If you find a chat bank at `chat-kvision-ws-client-1935385562-Wilfred Brimley.bank`, the corresponding world bank is `kvision-ws-client-1935385562.bank` (no `-<persona>` suffix). Same id means same session.

```bash
# Find all banks for one session id
ls ~/.tpipe/TPipe-Default/memory/lorebook/ | grep '<id>'

# Cross-reference a specific persona to its world bank
PERSONA_BANK=chat-kvision-ws-client-1935385562-Wilfred\ Brimley.bank
ID=$(echo "$PERSONA_BANK" | sed -E 's/chat-kvision-ws-client-([0-9]+)-.*/\1/')
ls ~/.tpipe/TPipe-Default/memory/lorebook/kvision-ws-client-${ID}.bank
```

When the world bank exists, **read both** — the chat bank shows the persona's voice; the world bank shows the game's response (often much longer than the persona's entry, including the AI's verbatim summary of game-state changes).

## Grep recipes

```bash
# Find all lorebanks for a persona (case-insensitive substring match on the name)
ls ~/.tpipe/TPipe-Default/memory/lorebook/chat-*.bank | grep -i 'lord maple tree'

# Pull the verbatim first lines of every entry for one persona
python3 -c "
import json, glob
for f in sorted(glob.glob('/home/cage/.tpipe/TPipe-Default/memory/lorebook/chat-*-Wilfred Brimley.bank')):
    d = json.load(open(f))
    print(f'--- {f.split(\"/\")[-1]} ({len(d[\"converseHistory\"][\"history\"])} entries) ---')
    for h in d['converseHistory']['history']:
        print(h['content']['text'][:300].replace(chr(10), ' / '))
        print()
"

# Find world banks that mention a specific game-mechanic term
grep -l 'victory point' ~/.tpipe/TPipe-Default/memory/lorebook/kvision-ws-client-*.bank

# Find world banks that contain operator Q&A ("Who is winning", "What resources", etc.)
grep -l '"role": "user"' ~/.tpipe/TPipe-Default/memory/lorebook/kvision-ws-client-*.bank
```

## Anti-patterns

### Don't try to reconstruct game mechanics from the lorebanks alone
Lorebanks capture **narration**, not state. The game-state fields (`territory.pointValue`, `player.victoryPoints`, `world.karmaPoints`) appear in the world banks as JSON fragments the AI is reasoning about, but the lorebanks are NOT authoritative for "what is the current score." For that, the world model is held in `WorldManager` at runtime and the `saved-games/<gameId>/world.json` on disk.

### Don't confuse lorebanks with saved-game world.json files
`saved-games/<gameId>/world.json` is the **canonical game state** (territories, players, scores, action history) — written by `TurnHarness` after each turn. The lorebanks are **dialogue caches** — they hold the AI's narrative output per persona. They're complementary: world.json for state, lorebanks for narration.

### Don't read lorebanks in chronological file order
Multiple personas from the same session land in different files. To reconstruct one turn, you need to cross-reference by `<id>` (the websocket session id embedded in the filename), not by file mtime.

### Don't trust a single lorebank entry as the persona's complete voice
Some personas have only one entry in one bank (Judge Null — single line of unpersoning). Others have many entries across many sessions (Wilfred Brimley, Shitty Bob). The persona's "true voice" is the union across all their banks.