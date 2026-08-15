# Adding a New Comparison Target — Workflow

When the user asks to add a new "TPipe vs [competitor]" comparison page to ttt-site, the workflow is distinct from rewriting existing pages. This reference documents the pre-flight pattern, the versioned-report cadence, and the site-wiring checklist.

## The Koog v3 case study (June 12, 2026)

The 7th comparison target was TPipe vs JetBrains Koog. The research side of the workflow followed this pattern:

1. **Pre-flight scan** — `ls md/FINAL-report-tpipe-vs-koog*.md` returned three reports: v1 (May 12, 27KB, 54 sources), v2 (May 12, 27KB, 70+ sources, corrected methodology), and the v3 produced this session (June 12, 54KB, 85 sources, 561 lines). Reading the v2 first established the prior baseline.
2. **Read all thread-level findings** for the competitor — five files existed in `md/`: `03-koog-overview-findings.md` (10KB), `04-koog-architecture-findings.md` (10KB), `04-koog-deep-findings.md` (18KB), `05-head-to-head-findings.md` (17KB), `05-tpipe-vs-koog-findings.md` (11KB — note: this one contains a flawed "TPipe doesn't exist" finding from web-only research, superseded by v2/v3).
3. **Local TPipe docs scan** — 20 local docs read for internal capabilities, since TPipe has no public web presence. Authoritative for TPipe-side claims.
4. **Time-delta web verification** — Koog 1.0 shipped May 27, 2026 at KotlinConf '26, two weeks after the v2 report. Four targeted web searches surfaced the new release data, including the PR-level release notes from `newreleases.io` and the ACP product page from `jetbrains.com/acp`. The delta check initially added a 12th dimension (Ecosystem/IDE Integration) to the comparison matrix where Koog's ACP integration was a documented win. **This dimension was retracted in a corrected v3** — see "Editorial revision pattern" below.
5. **Synthesis** — v3 written to `md/FINAL-report-tpipe-vs-koog-v3.md`, superseding v1 and v2. Citation table extended from 23 sources (v2) to 85 (v3).
6. **Hindsight retain** — three structured findings stored for cross-session recall: the comparison verdict, the Koog 1.0 release summary, and the TPipe architectural moat inventory. Plus a fourth: the editorial revision record (corrected verdict + headless-first rationale).

The v3 report is the source of truth for the new card. The next session's job is to convert it into the `.astro` page following the existing `tpipe-vs-langchain.astro` structural template.

### Editorial revision pattern — retracting dimensions, not just adding them

The Koog case study also demonstrates the inverse move: the initial v3 added a 12th "Ecosystem/IDE Integration" dimension where Koog's ACP integration was a documented win. Per operator directive ("There's zero value in TPipe being integrated into IDEs, this can be left out"), the dimension was retracted in a corrected v3 — the verdict went from "8 of 12, 1 Koog win" to "8 of 11, 0 Koog wins." The retraction was explicitly documented in an "Editorial Note" at the top of the corrected v3 and in a "Note on v3 editorial revision" line at the bottom.

When a v(N+1) retracts a dimension that vN added, the editorial note should:
- Name the retracted dimension
- Cite the operator directive or strategic reason
- Restate the corrected verdict count
- Link the two versions so a future reader can see the change

Don't silently omit a dimension that was in vN — that's a vN+1 bug pattern, not a vN+1 improvement. See the "Never score an IDE/editor integration dimension" rule in the main skill for the strategic reason this rule exists.

## The versioned-report pattern