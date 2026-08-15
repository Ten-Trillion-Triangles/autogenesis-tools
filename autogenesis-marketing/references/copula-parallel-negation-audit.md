# Copula-Avoidance / Parallel-Negation Audit — Mechanical Workflow

## The rule

The Bigwang pitfall #13 ban on "X is not Y, X is Z" / "is not Y but Z" / "isn't Y, X is Z" applies to EVERY sentence of body prose, including contractions (`hadn't`, `didn't`, `won't`), period-separated variants (`X is not Y. X is Z.`), and parallel structures (`X are not Y, X are Z`). The humanizer pass bans it; the principle generalizes. **When the rule is in context and the agent still bleeds it into the prose, the rule alone is not enough — the audit must be mechanical.**

## Why single-rule audits fail (verified 2026-08-12)

The bigwang skill carries pitfall #13 with a worked narrow grep. The autogenesis-marketing skill carries the "audit must run against the WHOLE DRAFT SET" principle. **Both rules were loaded. Both rules fired 11+ times in a single draft set of three Section 3 drafts.** The grep that was supposed to catch the pattern was insufficient on three axes:

1. **Contractions** — the v7 drafts contained `hadn't existed before` (in Draft A3). The broad `is not` grep missed it; the narrow grep (`is not \w+,? is`) missed it. Only the explicit contraction grep caught it on a re-audit.
2. **Period-separated variants** — `You are not playing against a board. You are playing against a world.` matched the narrow comma grep but not the parallel-structure grep. A separate period-separated check is needed.
3. **Parallelism across draft sets** — the same closer was copy-pasted across three drafts (A2/A3/A4) without the audit catching that the bug lived in three places. A grep that returns 11 hits hides which draft each hit is in. The audit must report per-draft counts.

## Mechanical audit (run BEFORE writing any landing-page pitch draft set)

### Step 1 — Write all drafts first, then audit. NOT per-draft.

The human instinct is to write Draft A, audit, write Draft B, audit, write Draft C, audit. **This is wrong.** The audit at the end of Draft A passes because Draft A is fresh; by Draft C the agent has pattern-matched into the prose shape that includes the bug. **Write all drafts in the set first. THEN audit the whole set as one operation.**

### Step 2 — Per-draft grep with attribution

```bash
DOC=/path/to/draft-set.md

python3 << 'PY'
import re, sys
with open('/path/to/draft-set.md') as f:
    content = f.read()

# Find each draft's start line
draft_starts = []
for m in re.finditer(r'^##\s+Draft\s+([\w-]+)', content, re.MULTILINE):
    draft_starts.append((m.start(), m.group(1)))

# Build per-draft slices
slices = []
for i, (pos, name) in enumerate(draft_starts):
    end = draft_starts[i+1][0] if i+1 < len(draft_starts) else len(content)
    slices.append((name, content[pos:end]))

# Negation patterns — the FULL set, including contractions and period-separated
patterns = [
    (r"\b(is not|are not|isn['’]t|aren['’]t)\b", "is not / are not / isn't / aren't"),
    (r"\bnot\b[^.\n]{0,80}?,\s*[a-z]", "not X, Y parallel"),
    (r"\bbut not\b|\bnot just\b|\bnot only\b", "but not / not just / not only"),
    (r"\b(didn['’]t|doesn['’]t|won['’]t|can['’]t|hadn['’]t|hasn['’]t|wouldn['’]t|couldn['’]t|shouldn['’]t)\b", "contractions -n't"),
    (r"is not [^.]+\.\s*[A-Z]", "period-separated is not Y. X is Z."),
    (r"\bnot\b[^.\n]{0,80}?\.\s*[A-Z]", "period-separated not Y. X Z."),
]

# Run per-draft
print("=== PER-DRAFT NEGATION AUDIT ===\n")
total_hits = 0
for name, text in slices:
    draft_hits = 0
    for pat, label in patterns:
        matches = list(re.finditer(pat, text, re.IGNORECASE))
        for m in matches:
            # Show line in the file (best-effort)
            line_no = text[:m.start()].count('\n') + 1
            preview = m.group(0)[:60]
            print(f"  [{name}] {label}: line ~{line_no} — \"{preview}...\"")
            draft_hits += 1
    if draft_hits == 0:
        print(f"  [{name}] CLEAN")
    total_hits += draft_hits
    print()

print(f"TOTAL HITS: {total_hits}")
sys.exit(1 if total_hits > 0 else 0)
PY
```

**Exit code 0 = clean. Non-zero = at least one hit, do not ship.**

### Step 3 — Closer is the highest-risk site

The closer of each draft is structurally the most-likely place for the bug to land, because:

- The agent is most fatigued at the end of the draft.
- The closer is the most-tempting place to reach for contrast (`X is not Y, X is Z`).
- Closers across drafts in a set get copy-pasted, propagating the bug to all of them.

**Treat the closer as a separate audit region.** Extract the last 3-5 sentences of each draft and re-grep with the full pattern set. If any closer hits, rewrite ALL closers, not just the one that matched.

### Step 4 — Rewrite rule when the audit hits

When a draft hits, do NOT try to "fix" the negation by tweaking words. The pattern is structural — the agent reached for contrast because contrast felt like conviction. **Rewrite the sentence as a positive statement of what X IS**, full stop. Examples from the 2026-08-12 Section 3 rewrite:

| BEFORE (negation frame) | AFTER (positive statement) |
|---|---|
| `You are not playing against a board. You are playing against a world that has taken an interest in what happens next.` | `You play against a world that has taken an interest in what happens next.` |
| `The NPCs you deposed are not the NPCs you end up dealing with.` | `The NPCs you depose are the NPCs that come back.` |
| `The grudges you accumulated are not the grudges that come back.` | `The grudges you accumulated are the grudges that come back.` |
| `Lord Maple Tree didn't write that. The world did.` | `Lord Maple Tree wrote the invasion. The world wrote the Nemesis.` |
| `The NPCs you spawn are not patterns you walk past.` | `The NPCs you spawn are characters with their own goals.` |
| `Not as a unit. As a Nemesis.` | `Three rounds later, General Moustache returned. As a Nemesis.` |
| `... an army that hadn't existed before.` | `... an army that was brand new, three rounds old.` |

Notice the last one: `hadn't existed before` looks innocent — single sentence, single contraction. But it IS the parallel-negation pattern in disguise: `X hadn't Y` → `X was Z`. Replace with positive construction.

### Step 5 — Re-grep after rewrite

After rewriting, re-run the per-draft grep. Show the operator the zero-match output. If any draft still has hits, rewrite again. Do not declare shipped until the grep returns 0 across the whole draft set.

## Failure modes this audit catches

- Single-draft negation patterns (the obvious cases)
- Contraction-wrapped negation (`hadn't`, `didn't`, `won't`)
- Period-separated variants (no comma to trigger the narrow grep)
- Parallel structures across multiple drafts (copy-pasted closers)
- Parallel structures within a single draft (e.g., three `X are not Y, X are Z` lines stacked)
- Implicit negation through comparison ("Most games... but here..." used as a closer frame)

## Failure modes this audit does NOT catch

- Hedged superlatives (`arguably the best`, `perhaps the most`)
- AI-tell vocabulary (`actually`, `fundamentally`, `essentially`, `it's worth noting`)
- Long-form structure problems (4th-wall breaks, address-to-reader closers)
- Tonal drift away from the operator's voice
- Factual claims (cite-source, not cite-component)

Those live in the humanizer pass (`creative:humanizer`) and the Bigwang audit checklist (pitfall #4 in the bigwang skill). This audit is ONE of the gates, not the only one.

## Cross-references

- `persona:bigwang` pitfall #13 — original rule statement and kill list.
- `autogenesis-marketing` SKILL.md § Anti-patterns — operator-confirmed failure pattern (parallel negation leaks into every draft in a draft set, not just one).
- `creative:humanizer` — full 29-pattern humanizer pass; run after this mechanical audit passes.