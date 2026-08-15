# Canonical Doc Discipline — Multi-Section Landing-Page Workflow

**Origin.** Operator-confirmed 2026-08-12 after the Autogenesis landing-page work produced 12+ draft files across four days and the operator asked: *"Ok lets go through all the docs so far and verify if thgey are matchinng what twe decided here in this chat so far."* The single-source-of-truth doc (`autogenesis-canonical-v10.md`) was the consolidation product.

This reference captures the workflow that produced the canonical v10 doc — what to do from the START of any multi-section landing-page work, not after the eighth draft.

---

## The failure mode this exists to prevent

Multi-section landing-page work generates a sprawl of draft files. The pattern:

1. **Day 1:** Hero copy. Drafts `drafts-v1.md` and `drafts-v2.md`.
2. **Day 2:** Hero sub copy. `draft-v3.md`. Section 2 copy. `draft-v4.md`.
3. **Day 3:** Section 3 copy. `draft-v5-section3.md`, `draft-v6-section3.md`, `draft-v7-section3-livingworld.md`, `draft-v8-section3-livingworld.md`, `draft-v9-section3-livingworld.md` (one draft per round of feedback).
4. **Day 4:** Section 4 + 5 reframes by operator. `section5-premise-pitch-v2.md`, `section5-what-a-turn-is-pitch.md`.
5. **Day 4, end:** "Where did we land? Verify all docs match what we decided." — operator has to reconstruct state across 12 files.

The pattern is linear — each piece of feedback spawns a new draft file. After four days the operator can't trust any single file to be canonical. They have to read all of them and reconstruct the current state in their head.

The fix: **produce a canonical file at the START of any multi-section landing-page work, with one section per heading and a status row per section. Add new sections to the canonical file as drafts arrive. Mark superseded drafts in their first line with `> **SUPERSEDED.**` so the sprawl doesn't fragment the source of truth.**

---

## The canonical doc shape

```markdown
# <Product> Landing Page — v<N> Canonical Copy

This is the canonical copy after the <date> audit. Every section here reflects either an operator-confirmed lock or the chief strategist's recommendation on the operator-supplied drafts.

---

## HERO (operator-locked)

<the canonical copy>

---

## SECTION 2 — "<section title>" (operator-locked)

<the canonical copy>

---

## SECTION 3 — "<section title>" (chief strategist's recommendation)

<the canonical copy>

---

## Status

| Section | Status | Source |
|---|---|---|
| Hero | LOCKED | Operator verbatim (chat) |
| Hero sub | LOCKED | Operator copy (chat) |
| Section 2 — "..." | LOCKED | Alt 2 (chat pick) |
| Section 3 — "..." | RECOMMENDED | Chief strategist's pick from <source-file> |
| ... | ... | ... |

## What still needs operator decision

1. ...
2. ...

## Supersedes

This file supersedes:

- `<obsolete-file-1>` — <reason>
- `<obsolete-file-2>` — <reason>
```

**Key features:**
- **One canonical file** with a clear name (`autogenesis-canonical-v10.md`, `landing-page-canonical-v2.md`, etc.) — not `draft-v3.md` or `working-draft.md` or `latest.md`.
- **Status table** — per-section row that names the section, its status (LOCKED / RECOMMENDED / DRAFT / TBD), and the source file the recommendation came from.
- **"What still needs operator decision" section** — open questions surfaced explicitly, not buried in body copy.
- **"Supersedes" section** — explicit acknowledgement that this file obsoletes other files.

---

## The SUPERSEDED banner pattern

Every obsolete draft gets a SUPERSEDED banner at the top of the file, immediately after the title. The pattern:

```markdown
# Autogenesis Landing Page — v4 Copy Draft

> **SUPERSEDED.** This file (Aug 9 14:28) was the first lock cycle. It contains four operator-confirmed locks (hero, hero sub, hero closer, Section 2) but its Section 3 (proof-cascade drafts) and Section 5 ("No two games are alike" lock) were both superseded by later operator work. Canonical copy now lives in `/home/cage/Desktop/Workspaces/md/autogenesis-canonical-v10.md`.

The operator accepted Draft F's hero through...
```

The banner must:
- Say "SUPERSEDED" prominently.
- Date the original creation.
- Explain WHAT replaced it and WHERE.
- Leave the rest of the file intact (don't delete the body — it's still readable for context).

This pattern keeps the obsolete drafts visible (you can see WHAT was tried) without confusing them with the canonical source of truth.

---

## When to create the canonical doc

**Create it before the third section draft, not after the eighth.**

Threshold: when you have three or more draft files in the working directory, you need a canonical file. Before three, the drafts are still legible on their own.

The first canonical file should be created with:
- All sections you've drafted so far.
- Status per section (LOCKED / DRAFT / TBD).
- A "What still needs operator decision" section.
- A "Supersedes" section listing the drafts it consolidates.

Then every new section gets added to the canonical file, NOT to a new draft file. Drafts become exploration documents for testing different framings, but the canonical file is the only "current state" doc.

---

## The audit-pass trigger

The operator has a single question they ask at certain points: *"Are these all matching what we decided?"* When they ask, run the audit:

1. List every draft file in the working directory.
2. For each file, classify as: LOCKED (matches canonical) / STALE (supersedes a section now in canonical) / REPLACEMENT (operator created to override a prior lock).
3. Update the canonical file's "Supersedes" section to include all obsolete files.
4. Prepend a SUPERSEDED banner to every obsolete file.
5. Update the canonical file's status table to reflect the current state.

This is a five-minute task. The operator's question is a signal that the draft sprawl has grown past legibility. Don't wait for the operator to ask. Run the audit proactively after every 3-4 draft iterations.

---

## Per-section reframe mechanic

When the operator creates a NEW pitch doc for a section that was already locked, treat the new doc as a **REPLACEMENT**, not a parallel option. The operator creates new docs to OVERRIDE prior decisions, not to add to them.

How to tell:
- The new file's header section usually says "v1 was rejected because…" or "operator caught X" or "operator is reframing."
- The new file usually has a different framing (not just a different copy) than the prior lock.
- The new file usually doesn't reference the prior lock by name — it's a fresh start.

When in doubt: assume REPLACEMENT. Update the canonical doc to remove the prior section copy. Add the new section copy. Mark the prior lock superseded. Add the operator's new pitch doc to the "Supersedes" section as the source of the new copy.

**Don't ask "which version do you prefer?"** — the operator created the new file because they already decided. They want the new file to replace the old one.

---

## Working draft vs canonical file — the rule

The line between "draft file" and "canonical file":
- **Draft file**: a single section, a single reframing, a single round of feedback. Lives until superseded.
- **Canonical file**: the single source of truth across all sections. Lives until the entire landing page ships.

The canonical file ALWAYS contains the current best copy for every section, even if some sections are "TBD" or "v4 form, never iterated." Empty rows in the status table are better than missing sections.

---

## Worked example: Autogenesis landing page v10

The canonical doc `autogenesis-canonical-v10.md` was produced on 2026-08-12 after the operator asked for the audit pass. It consolidated 12 obsolete drafts. Each obsolete draft was given a SUPERSEDED banner.

The status table at the end of v10:

| Section | Status | Source |
|---|---|---|
| Hero | LOCKED | Operator verbatim (chat) |
| Hero sub | LOCKED | Operator copy (chat) |
| Hero closer | LOCKED | Closer A (chat pick) |
| Section 2 — "What you write comes back" | LOCKED | Alt 2 (chat pick) |
| Section 3 — "The Living World" | LOCKED | Operator's `section3-final-A4.md` |
| Section 4 — "A turn is what the world does with what you wrote" | RECOMMENDED | Chief strategist's pick from `section5-what-a-turn-is-pitch.md` (Draft 5A) |
| Section 5 — "Anything you can imagine. The game builds around it." | RECOMMENDED | Chief strategist's pick from `section5-premise-pitch-v2.md` (Draft 5-premise-A) |
| Section 6 — "Create your commander" | v4 form | Never iterated |
| Section 7 — "The studio" | v4 form | Never iterated |

Two sections are RECOMMENDED (not LOCKED) because the operator created the pitch docs but hasn't explicitly picked which draft. The recommendation column names the chief strategist's pick and the source file. The "What still needs operator decision" section surfaces this as an open question.

---

## Cross-references

- `autogenesis-marketing/SKILL.md` — the skill this reference supports. The "Per-section reframe happens on operator initiative" and "Ship a single canonical doc from the START" pitfalls reference this workflow.
- `creative:humanize` — for the post-draft humanizer pass on the canonical file before ship.
- `persona:bigwang` — for voice calibration on any operator-supplied copy that needs the Bigwang register.