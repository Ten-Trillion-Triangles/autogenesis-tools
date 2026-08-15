# Audit Existing Docs to Match Recent Code Changes

Reference recipe for "updating existing TPipe docs to reflect recent code changes." Different from `pumpstation-doc-set.md` (which is the new-doc workflow for a subsystem with no docs). This file is for the audit workflow where the docs exist, the code has changed, and the user wants the docs to track the code.

Use this when the user says:

- "Update docs to cover new features"
- "Review the last N commits and update docs"
- "Sync docs with recent code"
- "Public-facing vs internal-hidden logic — update docs accordingly"
- "Make sure the docs match the code"

## When this applies

The audit workflow is for incremental doc updates against an active codebase where:

- The docs already exist and have an established style (mirror the existing sibling — don't invent a new layout)
- The code has changed via a recent batch of commits (typically 5-30)
- The user wants targeted updates, not a rewrite
- Some commits are user-facing, some are internal — the line has to be drawn

If the docs don't exist for the subsystem, use `pumpstation-doc-set.md` instead. If the user wants a wholesale audit of all docs vs all code, this workflow applies but the scope is "all docs touched" rather than "this N-commit batch."

## Worked example — 2026-07-08 PumpStation audit

Session context:

- 29 commits in scope (`git log --oneline -29`), all PumpStation
- Branch: `main`, working tree clean
- All four affected docs already exist with established style
- User said: "Determine where docs need to be updated to cover new features that were added that affect users of TPipe. IE: Public facing changes vs internal hidden logic. And update the docs in accordance with the design pattern of our docs."

Outcome:

- 4 docs updated (`docs/containers/pumpstation.md`, `docs/core-concepts/pumpstation-magic-contracts.md`, `docs/api/pumpstation.md`, `docs/api/pumpstation-models.md`, `docs/core-concepts/tracing-and-debugging.md`)
- ~250 lines added
- 0 commits documented that didn't drive user-facing change
- 2 pre-existing doc drifts fixed in the same patches

## Workflow

### Step 1: Get the diff range and the current docs state in parallel

In one turn:

```bash
git log --oneline -29
git log --stat -29 --no-merges
git status --short
git branch --show-current
```

And search for the docs inventory:

```python
search_files(pattern="*.md", target="files")
```

The point is to have both the commits and the docs available before any classification work. Don't react between these reads.

### Step 2: Classify each commit (Phase 2.5 in SKILL.md)

For each commit in the diff range, apply the line-drawing test:

> *Would a developer consuming this library as a dependency observe a behavior change?*

Documented examples from the PumpStation audit:

**User-facing — YES, document it:**

| Commit | Why user-facing |
|---|---|
| `fdcb98e5 feat(path-request): add nullable pathSelectionRationale field` | New field on `@Serializable` data class. Wire format changed. Every consumer who deserializes a `PathRequest` sees the new field. |
| `e6fc7b5e feat(station): mirror requirePathSelectionRationale with builder setter + DSL` | New builder setter (`setRequirePathSelectionRationale`) + new DSL var. Public API surface grew. |
| `afdb310d feat(prompt): add conditional rationale directive to path-injection` | New magic-contract field. The dispatch LLM now sees a directive in its prompt; the contract surface grew. |
| `a998e49e feat(harness): soft-nudge dispatch LLM when rationale is empty and policy is on` | New harness behavior: if `requirePathSelectionRationale=true` and the LLM emits null, the next dispatch prompt gets a reminder. What the LLM sees changed. |
| `016e1a98 feat(pumpstation): surface path-safety reason via verdict parser` | The parser now extracts `reason` and the harness propagates it. Behavior change in a documented phase (path-safety). |
| `3f8193d9 fix(pumpstation): surface path-safety rejection in next dispatch prompt` | Same as above but at the dispatch surface. Behavior change visible to the LLM. |
| `aa5a26c7 fix(pumpstation): HarnessCompleted funnel carries exitReason + finalOutput` | The `HarnessCompleted` event shape changed. Trace consumers see the new fields. |
| `59fccf40 fix(pumpstation): classify path timeouts as PathTimeout, not PathExecutionException` | New value in `PumpStationError` enum. Consumers who switch on the enum see the new branch. |
| `eb470d49 fix(pumpstation): reset loop-guard counter after trip` | Behavior change in loop-guard phase. Trace consumers see the trace event change. |
| `94578989 fix(pumpstation): omit null token fields instead of writing -1 sentinel` | JSON output shape changed (the trace events now omit null fields). Any consumer parsing the trace JSON sees the difference. |
| `f3774383 Fix accidental non elvis call` (the `InternalInterventionResult` change) | Internal `InterventionResult.result` is now nullable. The field is internal, but the agent-result shape changed — borderline. Did NOT document because the field is internal; mention in passing if relevant. |
| `fe719415 Expand tracing visualization to cover token spread` | New visualizer surface — HTML/JSON trace export renders a new element. |
| `d91fc736 Fix harness bugs and improve tracing` | Multi-file tracing improvements across 4 containers — user-facing because the visualizer output changed. |
| `1eba498b fix(pumpstation): embed turn history in judge + dispatch user prompts` | The judge and dispatch LLMs now see the turn history. Major correctness fix in a documented phase. Documented as the "Judge history injection (related fix)" subsection. |

**Internal-only — NO, skip:**

| Commit | Why internal |
|---|---|
| `77765f73 style(pumpstation): rewrite operator-narration comments as code comments` | Comment-only rewrite. No behavior change. |
| `18a62013 test(pumpstation): pin B7 omit-on-null token contract (replace -1 sentinel test)` | Test pin. The production behavior is unchanged. |
| `c50f6502 fix(test): stub-07 path-safety loop enqueue` | Test stub fix. |
| `4336be89 test(pumpstation): document B5 stub queue invariant` | Test stub invariant doc. |
| `126b3878 fix(test): replace StubOpenAIServer.stop(0) with stop(2) grace window` | Test server lifecycle. The doc explicitly says "pure test-side bug — production HTTP client is correct in isolation." |
| `eb470d49 test` half | Wait — the production change in `eb470d49` IS documented (counter reset), but the test file added in the same commit is internal. Classify each commit by what it changed, not by file. |
| `89340d9a fix(pumpstation): dedup rationale nudge per run` | Wait — this IS user-facing (the soft-nudge behavior changed to dedup per-run). Classify by behavior, not by file title. |
| `fff86b72 refactor(pipe): move buildDefaultPathInjection to file scope for test visibility` | Helper visibility refactor. No public surface change. |
| `484e4a63 test(trace): pin dispatch-event surface for pathSelectionRationale` | Test pin. The trace event surface itself is already documented. |
| `190b3068 merge: bring 8 PumpStation bug fixes into Pumpstation-Prune` | Merge commit. The 8 commits inside it have their own classifications. |

The decision rule, when a commit touches both production and test files:

1. Did the production code change behavior that a consumer sees? YES → user-facing.
2. Is the test pin/rename/stub fix documenting or fixing something that was already true? YES → internal-only.

When in doubt, grep the source for the symbol the commit added/removed/changed, and check if the symbol exists on a public class. If yes, user-facing. If internal/private, internal-only.

### Step 3: Find every doc that needs to change for each user-facing commit

For each user-facing commit, grep the docs to find which doc files reference the symbol. The right doc is the one whose subject is the symbol's class. Example:

- New field on `PathRequest` → `docs/api/pumpstation-models.md` (data class ref) + `docs/containers/pumpstation.md` (conceptual doc that uses the data class) + `docs/core-concepts/pumpstation-magic-contracts.md` (contract ref)
- New enum value on `PumpStationError` → `docs/api/pumpstation.md` (enum list in API ref) + maybe `docs/containers/pumpstation.md` (failure-modes subsection)
- New magic-contract behavior → `docs/core-concepts/pumpstation-magic-contracts.md` + `docs/containers/pumpstation.md` (which has a "Path-Safety Agent Contract" section that mirrors the magic-contract doc)
- New visualizer surface → `docs/containers/pumpstation.md` (Tracing Support section) + `docs/core-concepts/tracing-and-debugging.md` (the cross-cutting visualizer doc)

In the PumpStation audit, the `pathSelectionRationale` feature landed in 3 docs because the magic-contract doc, the container doc, and the API ref all have a `PathRequest` data class example. Three of three docs had to be updated for the same field. This is normal — TPipe docs are intentionally redundant at this level because different readers approach from different angles.

### Step 4: Read the source before writing each doc change

For each user-facing commit:

1. Open the source file the commit modified
2. Find the data class / enum / function definition
3. Copy the EXACT shape from the source into the doc — including field order, defaults, types

Do NOT copy from another doc. The other doc may have drifted (the magic-contracts.md repair-prompt example showed `inputData` instead of the real `pathSchema` — drift, but propagated by future writes).

### Step 5: Match the existing doc style

Each doc file has an established style:

- `docs/containers/<name>.md` — opens with a `> 💡 **Tip:**` callout, has a TOC, uses tables and code blocks, ends with "See Also" or "Cross-References"
- `docs/api/<name>.md` — exhaustive reference, one function per `####` heading, `**Behavior:**` for behavior descriptions
- `docs/core-concepts/<name>.md` — concept-driven, less rigid structure than API ref, more cross-references

The user said "in accordance with the design pattern of our docs" — that means **mirror the sibling doc**, do not invent a new layout. When adding a new section:

- The new section header level matches its siblings (usually `###` for the second-level entry under a `## Architecture` parent)
- The new section's tables match the column order of its siblings
- The new section's code blocks use the same indentation style and backtick count
- The new section's prose matches the existing voice (no conversational asides, no "let's dive in," no "as we saw above")

### Step 6: Patch the doc with the smallest viable change

Use `patch` with `old_string` matching a unique block and `new_string` adding the new content. Do NOT rewrite whole files.

Conventions:

- Adding to an existing table → find the unique last-row pattern, append a row after it
- Adding a new section → find the unique section-anchor, insert after it
- Updating a data class example → find the unique data-class block, replace with the updated one

When the patch fails to apply (because the file content drifted since you read it), re-read the file before retrying. Don't retry a stale patch.

### Step 7: Cross-document verification (Phase 4.5 in SKILL.md)

After updating N docs that share a feature, verify the cross-references are consistent:

```bash
# Pick the symbol name, grep all docs
grep -rn "pathSelectionRationale" docs/
grep -rn "requirePathSelectionRationale" docs/
grep -rn "PathTimeout" docs/
```

Every doc that references the symbol must agree on:
- The symbol name (case, alias vs canonical)
- The default value
- The cross-reference anchor — verify the anchor exists at the target (markdown anchors are derived from heading text, lowercase, hyphenated, punctuation stripped)
- The data class shape (the `@Serializable` data class shown in prose must match the actual source — same fields, same types, same defaults, same order)

```bash
# Verify the data class shown in prose matches the actual source
# Open the doc, find the @Serializable data class example, compare to the actual source
```

```bash
# Verify JSON schema examples match the @Serializable shape
# Open the doc, find the JSON example, compare to the data class
```

```bash
# Fence balance check — every modified doc must have an even number of ``` fences
for f in docs/containers/pumpstation.md docs/api/pumpstation.md docs/api/pumpstation-models.md docs/core-concepts/pumpstation-magic-contracts.md docs/core-concepts/tracing-and-debugging.md; do
  echo -n "$f: "
  grep -c '^```' "$f"
done
```

In the PumpStation audit:
- `pumpstation.md`: 80 fences (balanced — 40 blocks)
- `pumpstation.md` (api): 12 fences (6 blocks)
- `pumpstation-models.md`: 52 fences (26 blocks)
- `pumpstation-magic-contracts.md`: 46 fences (23 blocks)
- `tracing-and-debugging.md`: 83 fences (41.5 — odd, need to investigate)

If any doc has an odd count, you have an unbalanced fence. Find it and fix.

### Step 8: Final review

```bash
git diff --stat HEAD -- docs/
git diff HEAD -- docs/ | head -200
```

Walk through the diff visually:

- Each user-facing commit drove a corresponding doc change (no orphans)
- No internal-only commit drove a doc change (no noise)
- Each doc change is targeted (no drive-by rewrites)
- The pre-existing drift in touched sections is fixed

## Pre-existing drift found during the audit

Two pre-existing drifts were caught and corrected in the same patches that added the new behavior:

1. **`docs/core-concepts/pumpstation-magic-contracts.md` Repair on Parse Failure example.** The example JSON schema showed `inputData` (a non-existent field) instead of the real `pathSchema` field. The audit corrected this in the same patch that added `pathSelectionRationale` to the schema. The drift was probably introduced by an earlier agent that imagined a richer schema than the data class actually has.

2. **`docs/core-concepts/pumpstation-magic-contracts.md` Round-Trip a PathRequest example.** The example used the stale `PathRequest(pathName, pathSchema)` shape, missing the new `pathSelectionRationale` field. Corrected in the same patch.

**Rule:** when you patch a doc section, scan the section above and below your patch for stale JSON examples, stale data-class shapes, and stale cross-references. Fix them in the same patch — they're free wins that the user is paying for.

## Cross-cutting topics table gotcha

When the user-facing change adds a row to a cross-cutting table (e.g. `docs/containers/cross-cutting-topics.md` has implementation-status tables, kill-switch tables, tracing tables), the new row must match the row format of the surrounding rows exactly. The PumpStation audit did NOT touch `cross-cutting-topics.md` because the PumpStation changes didn't touch the implementation-status or kill-switch tables there — those tables track Manifold/Junction/Splitter status, not PumpStation feature additions. Verify before assuming.

## What to NOT document

Test stub quirks (`StubOpenAIServer.stop(2)`, queue invariants, sentinel-vs-null test pins), comment rewrites, helper visibility refactors, linter fixes, whitespace-only diffs. Documenting these pollutes the docs with noise that no consumer cares about and drifts faster than the production code. The line-drawing test catches all of these: would a library consumer observe this? No → skip.

## Things to verify checklist

Before declaring the audit complete:

- [ ] Every user-facing commit drove a doc change (no orphans)
- [ ] No internal-only commit drove a doc change (no noise)
- [ ] Each doc change is targeted (no drive-by rewrites, no whole-file rewrites)
- [ ] Every cross-document reference resolves (the anchor exists at the target)
- [ ] Every data class shown in prose matches the actual source (same fields, same types, same defaults)
- [ ] Every JSON schema shown in prose matches the @Serializable data class
- [ ] Every enum value, event type, and method name in prose appears in the source
- [ ] Every path:line reference points to existing code at that line
- [ ] Pre-existing drift in touched sections is fixed in the same patch
- [ ] Fence balance is even in every modified doc
- [ ] The user's "design pattern of our docs" is honored (no LLM 4th wall breaks, no conversational preambles, no hedging)

## How to apply this to the next audit

1. Get the diff range (`git log --oneline -N`) and the docs state (`search_files *.md`) in one turn.
2. Read the affected source files (the data classes, enums, magic contracts) before any prose.
3. Apply the line-drawing test to every commit. Write down the user-facing vs internal classification.
4. For each user-facing commit, find every doc that references the symbol. Patch the smallest viable change in each.
5. Match the existing sibling-doc style. Do not invent a new layout.
6. Run the cross-document verification protocol (grep for the symbol, verify data class shape, verify JSON schema, fence balance).
7. Fix pre-existing drift in touched sections in the same patch.
8. Final review with `git diff --stat` and a visual walk-through.

## Reference file produced

- `docs/containers/pumpstation.md` — canonical reference (received the bulk of the changes)
- `docs/core-concepts/pumpstation-magic-contracts.md` — magic-contracts ref (added rationale + reason-rides-back sections)
- `docs/api/pumpstation.md` — API ref (added `PathTimeout` to enum list, added `setRequirePathSelectionRationale` to builder-block code listing)
- `docs/api/pumpstation-models.md` — models ref (added `pathSelectionRationale` to `PathRequest`, added `requirePathSelectionRationale` to `PumpStationFailurePolicy`)
- `docs/core-concepts/tracing-and-debugging.md` — cross-cutting tracing doc (added Harness Token Spread Visualization subsection)

Total: 5 docs touched, ~250 lines added.

## Single-feature incremental update (lighter-weight path)

The 2026-07-10 Manifold `addWorker(component: P2PInterface)` / `workerP2P { }` doc edit was NOT a multi-commit audit — it was a single-PR update against a known good source. The 29-commit audit workflow above is overkill for that case. Use this lighter-weight path when:

- The user points at ONE code change (e.g. "rename X", "add the new DSL block to manifold.md", "addWorker renamed to addWorker(component)")
- The code change is already on a branch or merged and you have one or two source files in scope
- The doc targets are obvious from the change (the file the changed class lives in, plus any sibling docs that reference the old symbol)

### Procedure (six steps, not eight)

1. **Read the source change first.** Open the changed source file (e.g. `src/main/kotlin/Pipeline/Manifold.kt`), find the renamed/added surface (function, field, DSL block), and copy the EXACT signature into your mental model. For DSL blocks, also `read_file` the DSL file (`src/main/kotlin/Pipeline/ManifoldDsl.kt`) and verify the public setters match what callers will see.

2. **Grep the docs for the OLD symbol** (if a rename) or for related symbols (if a new DSL block). For renames: `grep -rn '<old_symbol_name>\b' docs/`. For new DSL blocks: `grep -rn '<related_block_name>' docs/`. The grep identifies which docs are touched (the ones that reference the old symbol, or the doc that hosts the related block).

3. **Read the affected doc end-to-end before editing.** Read the whole `docs/containers/<name>.md` (or `docs/core-concepts/<name>.md`) — not just the section you'll patch. This catches pre-existing drift in adjacent sections and tells you the doc's established voice for matching it. For a new DSL block specifically, the doc's existing `### block-name { }` section is the template for the new section's structure.

4. **Apply pitfall checks in the same patch.** Pitfalls #9 (pre-existing drift in touched section), #9a (renamed-symbol grep), and #9b (new-DSL-block coordination) all fire on the same edit. Apply them in one go.

5. **Verify every imported type in the new code example.** If you write a new DSL example that imports `Junction`, `P2PDescriptor`, `P2PRequirements`, `P2PTransport`, `P2PSkills`, `ContextProtocol`, `Transport` — verify each one resolves at the FQN you wrote:
   ```bash
   grep -nE 'class Junction\b|fun addParticipant\b' src/main/kotlin/Pipeline/Junction.kt
   grep -n 'class P2PDescriptor\b\|data class P2PTransport\b\|data class P2PSkills\b\|enum class ContextProtocol\b' src/main/kotlin/P2P/P2PDescriptor.kt
   grep -nE 'enum class Transport\b' src/main/kotlin/PipeContextProtocol/Pcp.kt
   ```
   Every FQN in the example's `import` block must hit a real class/enum/object. This is the verification gate that catches "looks right but is wrong" examples before they ship.

6. **Run the cross-doc verification protocol** (Phase 4.5 in SKILL.md) on the symbol you added/renamed. Grep all docs for the symbol name (camelCase and snake_case if relevant), confirm the cross-reference anchors resolve, and confirm the data class shape in any prose matches the actual `@Serializable` data class. Fence balance check on the modified doc.

### Worked example — 2026-07-10 Manifold `addWorker(component: P2PInterface)` doc edit

Session context:

- One PR on `main` (commit `8404811b`) that added `workerP2P { }` DSL block + `addWorker(component)` canonical method + renamed `workerPipelines` to `workerComponents` internally
- Three source files changed (`Manifold.kt`, `ManifoldDsl.kt`, `ManifoldDslTest.kt`)
- Two docs targeted: `docs/containers/manifold.md` (the canonical Manifold doc, 842 → 934 lines, +124 net) and `docs/core-concepts/killswitch.md` (the kill-switch propagation example, +5 net)
- Cross-doc renames handled: `addWorkerPipeline(...)` preserved as delegating sugar, mentioned everywhere as the backward-compat path

Outcome:

- 2 docs touched
- 1 new DSL block section added to manifold.md (`### workerP2P { }`) with a working Junction example
- 1 new accessor subsection added (`### Worker Accessors`)
- 1 dead-code example fixed in killswitch.md (`manifold.workerPipelines[0].killSwitch` → `manifold.getWorkerPipelines()[0].killSwitch`)
- All five Worker Pipelines / addWorker / addWorkerPipeline references in manifold.md updated to the new canonical/sugar split

Verification:

- `grep -rn 'workerPipelines\b' docs/` → 0 hits (the only remaining `workerPipelines` is the trace-key string `"workerPipelines"`, intentionally stable)
- `grep -rn 'addWorker\b' docs/` → 8 hits, all consistent with the new canonical method
- `grep -rn 'addWorkerPipeline\b' docs/` → 6 hits in manifold.md (intentional sugar references) + 1 in p2p-registry-and-routing.md (correctly using sugar on a Manifold instance)
- New Junction example imports every type by FQN — verified each against `src/main/kotlin/...` before commit