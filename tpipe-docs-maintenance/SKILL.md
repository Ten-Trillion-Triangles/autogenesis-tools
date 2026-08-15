---
name: tpipe-docs-maintenance
description: Systematic audit of TPipe code changes vs documentation AND sync of TPipe source docs to the ttt-site Astro project. Covers (a) what TPipe code needs documenting, (b) what TPipe source docs need updating, and (c) running scripts/sync-tpipe-docs.cjs (with optional TPIPE_DOCS env override) plus the visual/mobile audit of the ttt-site result. Load when user asks to "update docs", "audit docs", "sync docs with code", "sync docs to site", "mirror TPipe docs to ttt-site", "run the docs sync", "add a new section to the docs hub", or "review changes vs docs".
tags: [tpipe, documentation, audit, api-docs, release-prep]
---

# TPipe Documentation Maintenance

## Purpose
Systematic approach for auditing TPipe code changes, determining what documentation needs updates, and executing those updates. Covers both API reference docs and standard/getting-started docs.

## When to Load
- User says "update docs", "audit docs", "sync docs with code", "review changes vs docs"
- User says "sync TPipe docs to the site", "mirror docs to ttt-site", "run the docs sync", "run scripts/sync-tpipe-docs.cjs"
- User complains about null prevDoc/nextDoc on middle-of-chain docs ("no null in the middle" — see gotcha #13)
- User says "write docs for X", "document PumpStation/Manifold/Junction/...", "give X a doc set", "X has no docs, write them" — see "Writing new docs for a TPipe subsystem" below
- User says "magic contracts are missing", "the contracts aren't documented", "where do the data classes live" — load this to find the data-class-locations requirement and the magic-contract coverage expectation
- User adds a new top-level docs section to TPipe (e.g. "I just added a `superpowers/` directory") — see the 3-place update pattern in [references/ttt-site-docs-sync.md](references/ttt-site-docs-sync.md) §5
- User asks to update existing docs to reflect a single code change (e.g. "addWorker renamed to addWorker(component)", "rename X", "add the new workerP2P DSL block to manifold.md") — this is NOT the multi-commit audit workflow; it is a single-feature incremental update. Apply the pitfall checks below (especially pitfall #9 for pre-existing drift, #9a for renamed-symbol grep, #9b for new-DSL-block coordination) plus the Style Constraint. See the Common Pitfalls section.
- After significant code changes are merged to TPipe
- When preparing a release and docs need to match code
- When the user wants a visual/mobile audit of the ttt-site docs pages

## Workflow

### Phase 1: Gather Context

**Use a branch-anchored diff, not a rolling `-N` log.** When the user points at a feature branch (e.g. "examine the changes from the upgrade branch"), anchor the diff range to the merge-base or pre-branch-tip SHA so unrelated commits from main don't pollute the inventory. The current TPipe branch convention is `git log <merge-base-or-base-sha>..HEAD` paired with `git diff --stat <base>..HEAD`.

```bash
# Branch-anchored diff (preferred when user names a branch)
git branch --show-current
git log --oneline <base-sha>..HEAD       # commits unique to this branch
git diff --stat <base-sha>..HEAD          # file-level change summary for the branch
git diff <base-sha>..HEAD -- ':!PumpStation/*' ':!build/*' ':!*.html'

# Rolling log (use only when no branch anchor is available)
git log --oneline -30
git diff --stat HEAD~10..HEAD -- ':!PumpStation/*'

# Find all .md docs
find . -name "*.md" -not -path "./PumpStation/*" | sort
```

The branch-anchored form catches the actual scope: a 19-commit upgrade branch that adds `setPerformanceConfig`, `setRequestMetadata`, `setPromptVariables`, `BedrockCallMetadata`, `applyGuardrailPrecheck`, and the per-`contentBlockIndex` streaming reassembly collapses to 7 distinct feature topics in the doc-update table. A rolling `-30` would also drag in unrelated fixups from main that the user did NOT ask to document.

Symptom of skipping this: "I documented a fixup commit from main that has nothing to do with the branch the user named." Fix by re-anchoring to `<base-sha>..HEAD` and re-running Phase 2.5.

### Phase 2: Analyze Changes

**Code changes to look for:**

| Change Type | Doc Location | Update Action |
|-------------|--------------|---------------|
| New enum values | `docs/api/<entity>.md` | Add to enum listing |
| New functions/parameters | `docs/api/<entity>.md` | Add function signature + description |
| New class properties | `docs/api/<entity>.md` | Add to Public Properties section |
| New container/container methods | `docs/containers/<name>.md` | Add to relevant sections |
| Version number bumps | `docs/getting-started/*.md` | Update all version strings |
| New module/feature | Both API docs + standard docs | Full coverage |

**Standard docs** (user-facing):
- `docs/getting-started/` — installation, first steps, setup
- `docs/containers/` — container how-tos
- `docs/core-concepts/` — concept explanations
- `README.md` — project overview

**API docs** (reference):
- `docs/api/pipe.md` — Pipe class reference
- `docs/api/pipeline.md` — Pipeline class reference
- `docs/api/dictionary.md` — Dictionary token counting
- `docs/api/p2p-interface.md` — P2P interface contract
- `docs/api/converse-history.md` — ConverseRole + ConverseHistory

### Phase 2.5: Public-Facing vs Internal-Hidden Classification

**The single most-skipped gate in this workflow.** Before touching any doc, classify each commit in the diff range as user-facing or internal. Most commits are internal-only and should NOT trigger a doc update. Doing the classification first prevents polluting the docs with test-stub quirks, comment rewrites, and helper-refactor chatter that no consumer will ever read.

The line-drawing test — apply it to each commit:

> *Would a developer consuming this library as a dependency observe a behavior change?*

- **YES → user-facing.** Document it.
- **NO → internal.** Skip it.

**Indicators of user-facing changes (YES):**

- New field added to a `@Serializable` data class — the JSON wire format changed, every consumer who deserializes sees it
- New value in a public enum (`PumpStationError.*`, `ConverseRole.*`, `PathRiskLevel.*`)
- New entry in a sealed event class (`PumpStationEvent.*` variants) — trace consumers see it
- New builder setter, DSL block, or public method on a public class
- New flag / setting on a `*FailurePolicy`, `*Settings`, `*Config` data class — defaults change behavior at the harness level
- New magic-contract field — JSON schema the LLM emits/receives changed
- New trace event type — `TraceEventType.PUMP_STATION_*` rows
- New visualizer surface — HTML/JSON trace export renders a new element
- New entry in the public `pump-station` skill's "Magic Contracts" table
- Behavior change in a phase that has a documented contract (e.g., "the rejection notice now includes the reason text" — same field shape, but what the dispatch agent sees changed)

**Indicators of internal-only changes (NO):**

- Tests, test fixtures, test stub quirks (`StubOpenAIServer.stop(2)` grace window, queue invariant pins, sentinel-vs-null test rewrites)
- Comment rewrites, KDoc rephrasings, code-comment-style fixes
- Helper visibility refactors (moving a helper from inside a class to file scope)
- Linter fixes, formatter fixes, whitespace-only diffs
- Type-system drift fixes that produce no behavior change
- Internal-only field renames (private val, internal fun) that don't propagate to a public symbol
- Bug fixes in test infrastructure that don't change the production code path

**Worked example — TPipe PumpStation audit session, 29 commits, 4 docs updated, ~250 lines added:**

The 29 commits covered the `pathSelectionRationale` feature (5 commits: feature-stack from nullable field to DSL setter to soft nudge), path-safety reason propagation (2 commits: parser fix + dispatch surface wiring), `HarnessCompleted` event shape (1 commit), `PathTimeout` enum value (1 commit), loop-guard counter reset (1 commit), internal-helper-result nullable (1 commit), tracing visualization for token spread (2 commits), judge-dispatch history injection (1 commit), and ~15 commits of internal/test-only fixes (comment rewrites, test pins, server lifecycle, helper moves). The classification line landed at ~14 of 29 commits as user-facing (48%) — though only 8 commits drove actual doc changes because the rest of the user-facing changes were already documented or were within the same feature stack.

When in doubt, **err toward not documenting**. Internal docs become noise; the user can read the source. Test fixes in particular should NEVER drive doc changes — if the production behavior is the same, the doc doesn't need to change.

The full audit-classification table and the specific commit-by-commit decisions are in `references/audit-existing-docs-workflow.md`.

### Phase 3: Determine Update Scope

**API docs update pattern:**
1. Find the relevant `docs/api/<entity>.md` file
2. Match new code constructs to existing doc structure
3. Add missing entries — enum values, function signatures, property definitions
4. Preserve existing formatting and section organization

**Standard docs update pattern:**
1. Check version strings in `installation-and-setup.md` and `first-steps.md`
2. Update dependency coordinates (`com.TTT:TPipe:X.Y.Z`) in both snippets and version catalogs
3. Check README.md for version references in quick-start examples

### Phase 4: Execute Updates

Use `patch` tool for targeted edits. Key patterns:

**Adding enum values:**
```
-old
+new
```

**Adding function documentation** — add after the last function in the same section, before the next `---` divider.

**Version updates** — use `replace_all=true` for version strings that appear multiple times in the same file.

### Phase 4.5: Cross-Document Consistency Verification

After updating N docs that share a feature (one feature typically lands in 2-4 docs at once: container ref + API ref + magic-contracts ref + tracing table), verify the cross-references are consistent.

**The verification protocol:**

1. **Pick a feature identifier** — the symbol name, the new field name, or the new enum value (e.g. `pathSelectionRationale`, `requirePathSelectionRationale`, `PathTimeout`).
2. **Grep all docs for the identifier.** Every doc that references it must agree on:
   - The symbol name (case, camelCase vs snake_case, alias vs canonical)
   - The default value (e.g. `requirePathSelectionRationale = true` everywhere, not "true" in one place and "True" in another)
   - The cross-reference anchor (e.g. `[Dispatch Contract: pathSelectionRationale](../containers/pumpstation.md#dispatch-contract-pathselectionrationale)` — the anchor must exist at the target)
   - The data class shape (the `@Serializable` data class shown in prose must match the actual source — same fields, same types, same defaults, same order)
3. **Verify the JSON schema shown in prose matches the actual @Serializable shape.** When you write a JSON example inline in a doc, copy it from the actual data class (read the source file's data class block) and not from another doc. The other doc may have drifted.
4. **Verify the data class shown in prose matches the actual source.** If doc A says `data class PathRequest(var pathName: String = "", var pathSchema: String = "")` and the source says `data class PathRequest(var pathName: String = "", var pathSchema: String = "", var pathSelectionRationale: String? = null)`, doc A is stale.
5. **Run a fence balance check.** For each modified doc:
   ```bash
   grep -c '^```' docs/<path>.md
   ```
   The count must be even (each `\`\`\`` opens or closes a block). Unbalanced fences produce broken-rendering pages.

The verification commands used in the PumpStation audit session are in `references/audit-existing-docs-workflow.md` § "Cross-document verification."

### Phase 5: Verify
```bash
git diff HEAD -- docs/   # Review all doc changes
git diff --stat HEAD    # Confirm expected file counts
```

## TPipe Version Coordination

TPipe versions (in `build.gradle.kts` at project root) increment together across all modules:
- `version = "X.Y.Z"` in root `build.gradle.kts`
- Same version in `TPipe-Bedrock/build.gradle.kts`, `TPipe-GenericOpenAI/build.gradle.kts`, etc.

When version bumps, update ALL of these in docs:
1. `docs/getting-started/first-steps.md` — dependency snippets
2. `docs/getting-started/installation-and-setup.md` — dependency snippets AND version catalog (libs.versions.toml section)
3. `README.md` — quick-start examples

## Exclusions

- **PumpStation** — always exclude from analysis. It's explicitly under development and should not appear in docs until functional.
- `.gradle/` — build artifacts, never touch

## Style Constraint (DO NOT Violate)
The user expects **surgical, targeted edits** — patch only what changed, do not rewrite whole files. When updating an API doc, find the nearest unique block and add the new entry. When creating a new doc, follow the existing format (overview → TOC → public API table → examples). Use `ollama-pipe.md` or `multimodal-content.md` as the template for new API docs.

**No LLM 4th wall breaks.** The user explicitly required: *"this has to be written like a professional software docs so don't do classic llm 4th wall breaks here."* This is a strong, persistent style preference for TPipe source documentation. Forbidden patterns:
- AI-style preambles ("In this document we will explore...", "Let's dive in...", "I hope this helps", "Of course!")
- First-person voice unless quoting a developer-facing API
- "As an AI" / "as a language model" framing
- Conversational interjections or hedging ("it's worth noting that...", "you might want to consider...")
- Apologies, sycophancy, or throat-clearing

Match the existing `manifold.md` / `junction.md` / `distributiongrid.md` style. Their openings are: a `> 💡 **Tip:**` callout, a direct definition, an immediate `## Table of Contents`. Their bodies are: tables, code blocks, `path:line` references, "See Also" footers, direct prose. The user is paying for engineering rigor, not conversation. Match the existing siblings.

### Prose patterns to actively avoid (humanizer pass for technical reference docs)

The `humanizer` skill catalogs 29 AI-ism patterns. Most target marketing/persuasive prose. The subset that *specifically trips up technical reference docs* (container, API, magic-contract, tracing) — these are the patterns the user has explicitly flagged in source-doc reviews. Run a grep against your prose before claiming shipped:

**The first-class offenders (forbid these outright):**

| Pattern | What it looks like in prose | Doc-grade fix |
|---|---|---|
| "X, not Y" tailing negation | "The reminder is **advisory**, not enforced" / "The field is **nullable by default**, not required" | Drop the negation. State the positive. `null` round-trip is the example: write "`pathSelectionRationale` is nullable" — not "nullable, not required." |
| "X is not Y. X is Z." double-sentence | "The reminder is **advisory**, not enforced: a poorly trained model can still emit null and the harness accepts it." (the explicit negation + the second sentence that just restates it) | Lead with what it is. Cut the second sentence if it restates the first. |
| "now carries / now supports / now extracts" historical framing | "The `reason` field is now extracted and surfaced" / "`PathRequest` now carries an optional rationale field" | Drop "now". State what it does today. The fact that it changed is irrelevant to the reader reading the doc. |
| Rule-of-three listings | "Each event is plotted as a horizontal bar sized by its token count, color-coded by phase, and grouped under the run's runId." | Two clauses, not three. If you can't drop a clause, the third is filler. |
| Em dashes as pause markers | "The harness surfaces the prompts for the agents it owns — and auto-injects the path descriptor protocol into the dispatch pipe." (em dash as a "ta-da!" beat) | Comma or period. Em dashes are fine in source code comments and table separators, not in prose. |
| Bold-as-emphasis | "The field is **nullable by default** — old LLM checkpoints..." | Plain text. If the prose is precise, bolding is redundant. |
| "Let's dive in / let's break this down" | Opening signposting | Cut entirely. Open with the table or the prose, not a meta-comment. |
| Verbs that inflate | "showcases", "underscores", "highlights", "fostering", "leveraging", "tapestry" | Replace with the specific action: "renders", "extracts", "includes", nothing. |
| Tail-hedging | "to silence the prompt" (tacked on after a clear instruction) / "if you want the prompt side to stay silent" | Cut the trailing qualifier. The instruction was complete without it. |
| "This is the X" topic introducers | "This is the loader pattern." / "This is how the dispatch loop works." | Cut. The reader knows what they came for. |
| "Without X, Y doesn't do much" / "X is not optional" | "Without this, the judge would grade against an empty `converseHistory`..." | State the consequence as a separate sentence if it's load-bearing. Otherwise cut. |

**The audit grep (run on every prose patch):**

```bash
# First-class offenders
grep -niE "\b(is not|isn't|won't|doesn't|aren't|not just|not only|not a|not the|not on|not in|not required|not optional)\b" <file>
grep -nE " — |—" <file>   # em dashes in prose
grep -niE "(showcase|underscore|highlight|foster|leverage|tapestry|seamless|cutting-edge|delve|robust|harness|elevate|empower|unleash)" <file>
grep -niE "(now carries|now supports|now extracts|now exposes|now propagates|now handles)" <file>
grep -niE "(let's dive|let's explore|let's break|here's what you need to know|without further ado)" <file>
```

**The fix workflow (visible audit):** when the user invokes humanizer on a doc, the audit is a deliverable. Show what changed and why. Group by pattern class (negation / rule-of-three / signposting / em-dash / "now X") so the user can see the class of fix, not just the surface edit. Be honest about what's still arguably AI — em dashes that remain, structure that still feels algorithmically clean, prose that could use one more pass.

**The posture for technical docs vs marketing prose.** Blog posts (see `ttt-site-blog`) get BigWang voice with swagger attached to research. Reference docs get *no voice at all* — they get tables, code blocks, and `path:line` citations. The same pattern (e.g., the "X is not Y" double-sentence) is a different severity in each: a style issue in blog prose, a content bug in reference docs because the reader is grep-validating. Default posture for reference docs is mechanical, not persuasive.

**Worked example — PumpStation audit session 2026-07-08.** Five prose patterns I introduced in the initial pass that the user rejected via the humanizer skill:
1. "The `reason` field is **extracted and surfaced**, not just stored" — `not just` tailing negation + bold-as-emphasis
2. "The dispatch agent's `PathRequest` **now carries** an optional free-text `pathSelectionRationale` field. The harness uses it as a graded-trace surface — judge agents can grade decision quality, debug visualizers can show why the model picked one path over another, and a soft prompt-side nudge enforces the field without hard-failing on parse." — "now carries" historical framing + em-dash-as-pause + rule-of-three listing (judge / debug visualizers / soft nudge)
3. "The reminder is **advisory**, not enforced: a poorly trained model can still emit `null`, and the harness accepts it." — bold-as-emphasis + "X, not Y" negation + tail-hedging
4. "Without this the judge graded against an empty `converseHistory` and produced fabricated 'no prior work' declarations." — "Without X, Y" template (load-bearing here, kept after the humanizer pass; flagged for review if it appears in future drafts)
5. "Each `PUMP_STATION_*` event with token usage is plotted as a horizontal bar sized by its token count, color-coded by phase (judge, dispatch, path, safety, intervention), and grouped under the run's `runId`." — rule-of-three (bar / color-coded / grouped)

All five were caught and rewritten in the visible humanizer pass. Pattern #4 was kept on review because the consequence *is* load-bearing; the others were trimmed.

**Magic contracts are first-class.** When documenting any TPipe class that has LLM-facing magic contracts (PumpStation's judge/dispatch/path-safety/health/lorebook/goal are the most elaborate example; Manifold's `TaskProgress`/`AgentRequest` are simpler), enumerate every contract with its data class name, parser function, file:line, strictness policy, and fallback. The user considers this a non-negotiable requirement. See `pump-station` skill's "Magic Contracts" section for the full table of PumpStation's eight contracts as the canonical example.

## Common Gap Patterns (DO NOT Skip These)

When auditing recent changes, explicitly check for these patterns — they recur frequently:

### MultimodalContent (docs/api/multimodal-content.md)
- `interuptPipeline` property and `interupt()` method
- `terminateAndPassPipeline()` method
- `saveSnapshot()` / `getSnapshot()` / `deleteSnapshot()` — explicit snapshot lifecycle (the auto-save via `useSnapshot` is documented; the explicit save methods often are not)
- `setDistributionGridDirective()` / `getDistributionGridDirective()` — DistributionGrid router helpers

### ConverseRole (docs/api/converse-history.md)
- `supervisor` value — frequently added without updating the enum listing in docs

### New Provider Pipes
- Any new pipe class under `TPipe-*/src/main/kotlin/` → create `docs/api/<provider>-pipe.md` if no doc exists
- GenericOpenAI example: covers OpenAI Chat Completions, Anthropic Messages, and OpenAI Responses modes with `ApiMode` sealed class

## Common Pitfalls

1. **Missing version catalog updates** — the `libs.versions.toml` section in `installation-and-setup.md` has its own `tpipe-version` variable. Forgot to update this even after updating dependency snippets.

2. **Partial enum updates** — adding new `ConverseRole` values but missing the trailing comma or adding to wrong position in enum block.

3. **API doc structure drift** — when adding new functions, preserve the `#### ` signature format and `**Behavior:**` description pattern used throughout the file.

4. **New sealed class without variant table** — when adding a sealed class variant (e.g., `ApiMode.OpenAIResponses`), add it to the existing mode table in the doc, not just the source.

5. **Writing new docs without matching the sibling format** — when writing a brand-new doc for a complex subsystem (e.g. `pumpstation.md`), copy the structure of an existing sibling doc (`manifold.md`, `junction.md`) and the matching API doc. Do not invent a new layout; the existing format is the contract. See "Writing new docs for a TPipe subsystem" below.

6. **Trusting your own enum/event-name recall** — after writing any table that lists enum values, event types, or method names, grep the source for the prefix you used and diff against your list. This is the single most common source of "looks right but is wrong" in technical docs.

7. **LLM 4th wall breaks in documentation** — opening with "In this document we will explore..." or "Let's dive in..." or any conversational preambles. The user explicitly requires professional software docs style. Match the existing `manifold.md` siblings. See "Style Constraint" above.

8. **Treating magic contracts as a footnote** — when documenting a TPipe class with LLM-facing magic contracts, do not bury the contract list in one paragraph. Each contract needs its own section with: default prompt text, required JSON shape, data class signature with `path:line`, parser function with `path:line`, strictness policy, and fallback behavior. PumpStation's `pump-station` skill has the canonical example.

9. **Touching a doc section without fixing the pre-existing drift in that section** — when the user asks to "update docs in accordance with the design pattern of our docs," they expect drift in the touched section to be corrected too. The PumpStation audit session caught pre-existing drift in `docs/core-concepts/pumpstation-magic-contracts.md`: the JSON schema in the "Repair on Parse Failure" example showed `inputData` (an invented field) instead of the real `pathSchema` field, and the round-trip example used a stale `PathRequest` shape missing the new `pathSelectionRationale` field. Both were corrected in the same patch that added the new behavior. **Rule:** when you patch a doc section, read the section above and below your patch for stale JSON examples, stale data-class shapes, and stale cross-references. Fix them in the same patch — they're free wins that the user is paying for.

9a. **Renaming a public symbol in code requires a doc-wide grep for the OLD name** — when a Kotlin source change renames a public field or method (e.g. `workerPipelines: MutableList<Pipeline>` becomes `workerComponents: MutableList<P2PInterface>` while a trace-key string `"workerPipelines"` survives for backward compatibility), documentation may carry a code-comment example that still uses the old field name (e.g. `// manifold.workerPipelines[0].killSwitch = KillSwitch(...)` in `docs/core-concepts/killswitch.md`). That example won't compile if a developer copies it. **Rule:** after a source-side rename, run `grep -rn '<old_symbol_name>\b' docs/` and patch every example that references the old name. The grep catches (a) compiled-example prose, (b) inline `// comment` snippets, and (c) JSON/data-class examples that show the old shape. Same-patch fix is mandatory — do NOT defer it as "pre-existing drift." Confirmed 2026-07-10 Manifold `workerComponents` refactor: `manifold.workerPipelines[0]` was a live code-comment example in `docs/core-concepts/killswitch.md` showing propagation; the source field had renamed but the doc example still read the old name. Note the trace-key string `"workerPipelines"` IS still public and stable — the grep needs a word boundary on the symbol as a Kotlin identifier, not as the trace-key string. The two coexist: `workerComponents` is the Kotlin field, `metadata["workerPipelines"]` is the trace dict key.

9b. **Adding a NEW DSL block or method to an existing container doc** — when the source-side change ADDS a new public surface (e.g. `workerP2P("name") { ... }` DSL block alongside the existing `worker("name") { ... }`), the doc update is more than a single-line insertion. Three coordinated edits in the same patch are mandatory: (1) the DSL Blocks table gets a new row at the same `|`-depth as the related existing row, (2) a new `### block-name { }` section after the related `### block-name { }` section with a working code example that uses ONLY real public API (verify every import path with `grep -nE 'class <Type>' src/main/kotlin/...` before shipping), (3) the section's prose must match the existing `### block-name { }` sections' voice — same opening phrasing, same bullet-list shape, same paragraph structure. If the existing sibling uses `### worker { }` then opens with "The `worker(\"name\") { }` block registers a worker pipeline. Each worker pipeline must..." then the new `### workerP2P { }` should open with "The `workerP2P(\"name\") { }` block registers any `P2PInterface` as a worker...". Mirror the structure, do not invent a new layout. TOC remains at top-level only (TPipe's sparse-TOC convention — `junction.md` and `distributiongrid.md` both follow this). Confirmed 2026-07-10 Manifold `workerP2P` doc edit: three coordinated edits to `docs/containers/manifold.md` (DSL Blocks table row, new `### workerP2P { }` section, `### Worker Accessors` subsection) plus the canonical-API vs backward-compatible-sugar paragraph at the bottom of the new section.

10. **Forgetting to do the Phase 2.5 public-facing vs internal-hidden gate** — without the gate, every commit in the diff range becomes a doc task. 29 commits becomes 29 doc changes, half of which document test-stub quirks and comment rewrites that no consumer will ever see. The docs end up longer, the user has to read past noise to find the signal, and the document-vs-code relationship becomes muddled (the doc starts tracking test infrastructure that drifts faster than the production code). **Rule:** always do Phase 2.5 first, before writing any prose. The line-drawing test ("would a library consumer observe this?") is a 5-second judgment per commit; total: under a minute for 30 commits. Skip the gate, spend an hour cleaning up noise later.

11. **Patching an API-surface doc without checking for duplicate section blocks** — when the doc target has duplicate chapter blocks (e.g. `TPipe-Developer-Manual.md` ships the same `### TPipe-Bedrock` section at TWO different line numbers because an earlier "module integrations" rewrite was never deduped), a `patch` call with `old_string` matching the unique block fails with "Found 2 matches for old_string." Two safe responses:

    - **Prefer `replace_all=true`** when the duplicated blocks are *intentionally* identical (the doc author wanted both copies). The patch will land on both copies in one call.
    - **Dedup the source first** when the duplicated blocks should be one section (the second copy is stale leftover). Pick the more current copy, delete the other, then patch the single remaining block with `replace_all=false` (default).

    **Diagnostic before patching:** `grep -n '^## \|^### ' <doc>` to see the heading layout. If two headings have the same text AND the same parent (e.g. both under `## Module Integrations`), they are likely duplicates. The TPipe-Developer-Manual.md case shipped both copies of the TPipe-Bedrock module section under both `## Module Integrations` instances at lines 147 and 381; both copies needed the same SDK version + builder-method updates from the 1.6.107 upgrade, so `replace_all=true` was the right call.

    **Symptom of skipping this:** a patch lands on the first match only and the second duplicate block silently goes stale. Worse: you re-read the doc post-patch, see the second block is still pre-upgrade, and re-patch — now the diff has two competing edits to the same logical section.

12. **Patching out-of-repo docs without verifying the user means the repo copy** — when a TPipe doc lives at `$HOME/<name>.md` (e.g. `/home/cage/TPipe-Developer-Manual.md`) instead of inside the repo, `git status` and `git diff` will not show the edit. Verify before patching: search for the doc name under both `$HOME` and the repo's `docs/` directory. If both copies exist, patch the one the user pointed at (or the canonical one) — but state which one was edited so the user knows the other copy still needs updating.

## Writing new docs for a TPipe subsystem

Different from the audit workflow above. Use this when a TPipe subsystem has no doc set yet, or its docs are obviously stale, and the user asks you to write them.

### Workflow

1. **Load the subsystem skill first.** TPipe subsystems have skills under `software-development/` (e.g. `pump-station`, `tpipe-pipeline-patterns`, `tpipe-generic-openai`, `graalvm-abi`). The skill lists the key files, the design philosophy, and the magic contracts. If the skill exists, load it via `skill_view(name)`. If it doesn't exist, check for a `docs/superpowers/specs/<date>-<feature>-design.md` design doc instead — that is the spec to follow.

2. **Read the spec / design doc end to end before touching the docs.** The design doc fixes the vocabulary (phase names, event names, contract shapes). Mis-naming a phase in your new docs because you didn't read the spec is the #1 way to ship inconsistent docs.

3. **Batch-read all related source files in one turn.** A complex TPipe subsystem spans multiple `.kt` files (main class, models, DSL, helpers, v3 additions, default prompts, examples). Issue all the `read_file` calls in parallel — don't read one, react, then read the next.

4. **Batch-read 1-2 sibling docs to learn the format.** Read a similar sibling (e.g. `manifold.md` for a new container doc, `lorebook.md` for a new API doc). Note the TOC pattern, the 💡 Tip callout, the table style, the source-file references with `path:line`, the "See Also" footer. Match it.

5. **Batch-read the test fixtures and one or two integration tests.** Tests encode the magic contracts: the JSON shape the judge must return, the required setup that throws on missing pieces, the kill switch trip behavior, the path execution priority chain. These are the most valuable source of "required setup the developer must know" content.

6. **Write the docs in this order** (don't write the API reference first — it's the longest, not the most important):
   - Main container / reference doc (`docs/containers/<name>.md`) — architecture, exit mechanisms, modes, how-to, anti-patterns
   - How-to / magic-contracts doc (`docs/containers/<name>-how-to.md`) — the recipes developers actually copy
   - API reference (`docs/api/<name>.md`) — exhaustive method/class index
   - Update cross-references in existing docs (overview, cross-cutting-topics, README nav) in the same commit

7. **Verify every enum value, method name, and event name against the source.** After writing any table that lists these, grep the source:
   ```bash
   grep -n "PUMP_STATION_" src/main/kotlin/Debug/TraceEventType.kt
   grep -n "PathLimitExceededPolicy" src/main/kotlin/Pipeline/PumpStationModels.kt
   ```
   If your doc says `HandedOffToTruncation` and the enum says `HandedOff`, you ship a bug. This is the single biggest class of error in fresh-from-code docs.

8. **Verify line-number references.** Anywhere you cite `PumpStation.kt:1578`, open the file and confirm the line is still there. Line numbers drift fast in active branches; if the file is small enough, re-read the cited block.

9. **Don't pad.** The user can read the source. The doc's job is the architecture, the contracts, and the recipes — not a verbatim restatement of every method. If a method is one line and obvious, link to it, don't explain it.

10. **For magic contracts: distinguish "default" from "your responsibility".** Most TPipe harnesses auto-inject default system prompts and read `MultimodalContent` flags. The moment the developer customizes a prompt, they own the contract. Surface this distinction in the how-to doc with a "what we inject vs what you supply" frame.

11. **Match the existing sibling style — no LLM 4th wall breaks.** Open with a `> 💡 **Tip:**` callout, not a conversational preamble. No "let's dive in" or "I hope this helps" anywhere. The Style Constraint block above lists the forbidden patterns.

### Output structure for a complex subsystem (the PumpStation template)

For a subsystem with multiple sub-concepts, three files is the right shape:

- `docs/containers/<name>.md` — main reference (architecture + modes + how-to in one doc, mirrors `manifold.md`)
- `docs/containers/<name>-how-to.md` — required setup, magic contracts, build recipes, anti-patterns
- `docs/api/<name>.md` — exhaustive API reference (mirrors `lorebook.md` for layout density)

Plus updates to:
- `docs/containers/container-overview.md` — add to container list
- `docs/containers/cross-cutting-topics.md` — add to tracing table, kill switch table, implementation status table, event list, nav
- `README.md` — add to container architecture section + API reference section

### Worked example

The PumpStation doc set is the canonical worked example for this workflow. See [references/pumpstation-doc-set.md](references/pumpstation-doc-set.md) for the full recipe, the things to verify, and the file shapes.

## Related Skills

- `pump-station` — domain skill for the PumpStation harness itself; load this before writing PumpStation docs (its `SKILL.md` is the source of truth for the architecture, magic contracts, and pipeline patterns)
- `tpipe-generic-openai` — covers TPipe-GenericOpenAI module specifics (streaming, API modes, SSE parsing)

## Reference Files

- `references/ttt-site-docs-sync.md` — ttt-site sync recipe (mirror TPipe source docs to the Astro marketing site)
- `references/pumpstation-doc-set.md` — Shape A/B decision and full worked example for writing brand-new docs for a TPipe subsystem (e.g. PumpStation's three-file or four-file doc set)
- `references/generic-openai-pipe.md` — TPipe-GenericOpenAI module specifics (when to make a separate module doc)
- `references/audit-existing-docs-workflow.md` — **audit workflow** for updating existing docs to reflect recent code changes. Worked example from the 2026-07-08 PumpStation session (29 commits, 4 docs updated, 250 lines added). Covers the public-facing vs internal-hidden line-drawing test, the cross-document consistency verification protocol, and the pre-existing-drift-in-touched-section trap.

## Style Constraint (DO NOT Violate)

- `templates/sync-tpipe-docs-deterministic.py` — drop-in Python replacement for the `scripts/sync-tpipe-docs.cjs` sync. Alphabetically chains per section and per subdir, guaranteeing zero in-the-middle null prev/next (the user's "no null in the middle" rule from gotcha #13). Also escapes YAML in titles/descriptions (gotcha #14). Use this when the user pushes back on nulls in middle-of-chain docs.