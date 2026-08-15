# Autogenesis NPC Cascade Turn — Detection & Extraction

A "cascade turn" is a turn where a player's previous action triggered an NPC
counter-response. Real example from corpus: `Round_2_Turn_1_Judge_Gaveltooth/`
(triggered by Shitty Bob's R1T3 chaos).

## Folder pattern (no NeoWritingAgent, no Judge, no MaintenanceSplitter)

```
{NPCName}/
├── NPC_Active_Turn/                                       # The NPC's actual action
├── NPC_CascadeTargetDetector_<TargetPlayer>_Depth0/        # Which player triggered the cascade
├── NPC_CounterResponseIntent_AI_UNREACHABLE_<TargetPlayer>_depth0/  # Intent; "AI_UNREACHABLE" = target is AI-controlled
├── NPC_PlayType/                                          # What kind of play the NPC is making
├── NPC_ResponseRefinement_<TargetPlayer>/                 # Refined response to target
├── NPC_TargetDetectors/                                   # Generic target detection
├── NPC_Validation/                                        # Validates the NPC's submission
└── AI_Counter_Response/<TargetPlayer>_<timestamp>.json    # In-flight AI-generated counter-narrative (15MB+, 80-100 events)
```

## Key signals

- `NPC_CascadeTargetDetector_Shitty_Bob_Depth0` → Shitty Bob's previous action
  triggered this turn. The `_<Player>_Depth0` naming pattern identifies the
  target of the cascade.
- `NPC_CounterResponseIntent_AI_UNREACHABLE_Shitty_Bob_depth0` →
  `AI_UNREACHABLE` is a system marker meaning the target player is AI-controlled
  and can't be directly messaged. The NPC is reacting to them, not
  communicating.
- `AI_Counter_Response/<Player>_<timestamp>.json` (15MB, 87 events, ends in
  `PIPE_SUCCESS`) → the in-flight AI synthesis for the target player's
  response to the NPC's action. The `_<timestamp>` suffix matches the
  `NPC_ResponseRefinement_<Player>/` directory timestamp.

## What a cascade turn contains

- `NPC_Active_Turn/trace.json` `PIPE_SUCCESS` of `npc actor pipe` → the NPC's
  actual narrative action. This is the readable NPC prose (e.g., Judge
  Gaveltooth issuing the warrant for Chaos Bob and Queen Chimney).
- The `Compliance Officer` schema-validation meta-text in the same turn is
  NOT the narrative — it's the NPC's submission validation, ~2300 chars of
  "I verify that the prior agent..." boilerplate. Skip it.
- The full NPC character profile lives in `API_CALL_SUCCESS` of the `author`
  pipe event (~2500 chars of `characterProfile` / `problemView` /
  `characterSolution` JSON). Extract this for the NPC's motivation, not the
  narrative.

## What a cascade turn does NOT contain

- No `NeoWritingAgent/trace.json` — no readable prose narrative rendered yet.
- No `Judge/trace.json` — no world-state impact computed yet.
- No `MaintenanceSplitter/.../updates/trace.json` — no stat changes committed
  yet.

The turn has fully executed the NPC's reactive action, but the world's
response to the NPC's action is still being computed. The post-mortem is
"in flight" — the cascade hasn't resolved into world-state changes yet.

## Worked example: Round_2_Turn_1_Judge_Gaveltooth (this corpus)

**Trigger**: Shitty Bob R1T3 (Greenland holy crusade, chimneys screaming,
microwave burrito achieves sentience). The "Duel of Defilement" + "Sacred
Chimney Blessing" + "burrito plotting revenge" chaos registered as
`karmaPoints` that pushed a counter-response over its threshold.

**NPC identity**: Judge Gaveltooth, a 40-foot T-Rex judge of the Moral
Tribunal enforcing Officer Dave's legal tyranny from the Repurposed Lollipop
Factory. Defined in `NPC_Active_Turn/trace.json` `API_CALL_SUCCESS` of the
`author` pipe, event #14.

**NPC's actual action** (`NPC_Active_Turn/trace.json` PIPE_SUCCESS of
`npc actor pipe`, ~2027 chars):
- Rises from throne of cereal boxes in the Repurposed Lollipop Factory.
- Activates the **Judicial Reach Protocol** and **Interpol Subsection Clause
  66.04: The Dave Amendment**.
- Extends Moral Tribunal jurisdiction to all territories exhibiting
  "unlawful absurdity and theatrical defiance of rational order."
- Issues warrant for Chaos Bob and Queen Chimney.
- Charges: Crimes Against Rational Order (Class Ω), Theatrical Rebellion in
  Sacred Judicial Silence, Unsanctioned Defilement of Geologic Chorales,
  Harboring Sentient Digestive Hazards (Burrito Accomplice Status Pending).
- Sentence: trial by digestion. If resisted, consumption of their entire
  ideological network — chimneys, cults, and microwave ovens alike.

**Target player counter-response** (`AI_Counter_Response/Shitty Bob_1781991109085.json`,
87 events, 15MB, ends in PIPE_SUCCESS of `Execution Stage (Shitty Bob)`):
- Chaos Bob is dispatched to **Nicaragua** under the guise of a UN sanitation
  inspector.
- Mission: shit in every government chimney and convert the presidential
  palace into a shrine of unregulated defecation.
- Cites "Chapter 9 from The Art of Chimney Defecation": "When the People
  Are Constipated, You Must Be the Laxative."
- Establishes the **Ministry of Harmonized Bowel Movements**.

**Cascade end-state**: The T-Rex judge issued a warrant. Chaos Bob is
heading to Managua. The microwave burrito is plotting revenge. The turn
folder ends with the counter-response complete but no narrative rendered.
The game is mid-cascade — next turn will likely be Shitty Bob's response
play or another NPC's reaction to the Judge Gaveltooth warrant.

## Post-mortem classification

Mark cascade turns as **"Cascade in flight — narrative rendered, world-state
pending"** rather than guessing outcomes. Extract:

| Building block | Source |
|---|---|
| NPC character profile | `NPC_Active_Turn` `author` pipe `API_CALL_SUCCESS` |
| NPC's actual action | `NPC_Active_Turn` `npc actor pipe` `PIPE_SUCCESS` |
| Triggering player | `NPC_CascadeTargetDetector_<Player>_Depth0/` folder name |
| Target's counter-response | `AI_Counter_Response/<Player>_<ts>.json` final `PIPE_SUCCESS` |
| Readable narrative prose | NOT YET WRITTEN (turn is mid-flight) |
| Judge verdict | NOT YET COMPUTED (cascade hasn't resolved) |
| World-state changes | NOT YET COMMITTED (MaintenanceSplitter absent) |

## Detecting cascade turns from a fresh trace root

```bash
# A turn is a cascade turn if it has NO NeoWritingAgent AND no Judge folder
turn_dir=~/.tpipe/debug/trace/<RoundN_TurnM_Player>
[ ! -d "$turn_dir/NeoWritingAgent" ] && [ ! -d "$turn_dir/Judge" ] && \
  [ -d "$turn_dir/NPC_Active_Turn" ] && echo "CASCADE TURN: $turn_dir"

# Extract the target player from the cascade folder name
ls -d "$turn_dir"/NPC_CascadeTargetDetector_* 2>/dev/null | head -1 | \
  sed -E 's|.*NPC_CascadeTargetDetector_(.+)_(Depth[0-9]+)/?$|\1 (\2)|'
```

## Why this matters

The cascade machinery is the substrate running the world's response to
player actions. The `AI_Counter_Response/<Player>_<ts>.json` 15MB trace is
the system generating the next player turn's action in response to the
NPC's warrant. That is the architecture the corpus is building toward: the
substrate doesn't just run player turns. It runs the world's response to
player turns.
