# Hero Closer Pattern — Reference for the operator-confirmed canonical close

## The locked closer (operator-confirmed 2026-08-12)

> **You write the moves. The world writes the consequences.**
>
> Every turn, the board records what happened. The next player has to deal with it.

## Why this lands (and what was rejected)

The earlier v4 closer *"Four players. Twenty-five rounds. One shared world. No two games are ever the same."* was rejected as weak. The operator's verdict: *"This part is weak."* The cause: three numbers and an abstraction. Numbers don't sell. Abstractions don't tell the reader what happens.

The locked closer answers the implied question — *what happens after I write the move?* — in two imperatives + one consequence:

1. **"You write the moves"** — first-person, the player
2. **"The world writes the consequences"** — third-person, the world responds
3. **"Every turn, the board records what happened"** — persistence promise
4. **"The next player has to deal with it"** — PvP-delayed-consequence in seven words

The fourth line is the load-bearing one. *"The next player has to deal with it"* is the PvP-delayed-consequence in seven words. It tells the reader: this is not a sandbox, this is not a chat — this is a PvP game where what you write comes back at you through the other players.

## What gets cut from the closer

The original v4 closer had a "rule-rewriting aside" appended after the locked hero line:

> *"Even that's only partly true — because very clever players can rewrite the rules of the world itself if they become powerful enough or clever enough to pull even that off. Even the sky can be demolished by Robert the Destroyer's demolition robots if he's determined enough."*

This MUST be cut. The operator's reaction to having it present was *"The action menu thing is not what I wanted"* (after the agent paraphrased the hero into a different shape, but the underlying principle is the same: don't append qualifiers to operator-locked punch lines, even from the operator's own transcript).

The rule-rewriting concept moves to a body section as a proof-clip, e.g.:

> *"A commander became so powerful they rewrote the laws of physics themselves."*

That belongs in the proof-clip cascade (Section 3 or Section 4), not in the hero. The hero's job is the punch. The body's job is the proof.

## Anti-patterns to avoid in the closer

- **Numbers without context** — *"Four players. Twenty-five rounds. One shared world. No two games are ever the same."* — three numbers + an abstraction. Weak.
- **Restating the goal** — the hero sub already says *"control the the world."* Don't repeat it in the closer.
- **Soft superlatives** — *"Powerful. Innovative. Unique."* — banned per the Bigwang pitfall #13 hedge list.
- **Generic call to action** — *"Play now and see."* / *"Try the demo today."* — the CTA buttons (Play in Browser, Watch a Turn) already do this work.

## Worked example: the v9 → canonical v10 closer flow

1. v4 closer = "Four players. Twenty-five rounds. One shared world. No two games are ever the same." → REJECTED
2. v6 closer draft A = "You write the moves. The world writes the consequences. Every turn, the board records what happened. The next player has to deal with it." → LOCKED
3. v9 closer preserves the locked line verbatim. The "play against a world that has taken an interest" closer in v8 was rewritten to drop the "not X, Y" parallel-negation pattern. The v9 closer is: *"You play against a world that has taken an interest in what happens next."* (single sentence, positive construction, no negation.)

For new HTML mocks, the v9 closer is the canonical. For new draft sets, lift it verbatim.

## Cross-reference

- `references/autogenesis-visual-system.md` — the hero CSS class structure (`.lede`, `.lede-final`, `.hero-actions`) and the rhythm of the hero copy.
- `references/premise-sentence-catalog.md` — the operator's verbatim input that produced the locked hero copy.
- `references/copula-parallel-negation-audit.md` — the audit pattern that catches the v8 negation violation.
- `references/canonical-doc-discipline.md` — the workflow rule that the locked closer gets the SUPERSEDED banner in any draft file that's been rolled into the canonical.
