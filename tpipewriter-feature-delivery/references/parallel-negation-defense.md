# Parallel-Negation Defense — Reference

## Why this block exists

Chatbot-tuned LLMs overproduce `"not X but Y"` / `"it's not X, it's Y"` as a cheap-contrast device when asked to rewrite prose. The defense is a teaching block injected into writer-pipe system prompts that lists 8 variants, names the rule (`Never lead with the negation`), and pins the surgical-replacement mode (`mode is always "replace"`).

## Teaching block (canonical)

Header literal: `##STYLE: NO PARALLEL-NEGATION CONSTRUCTS`

Variant list (8 entries, in source order):

1. `"Not X but Y"`
2. `"It's not X, it's Y"`
3. `"Not because A but because B"`
4. `"Not A but B"`
5. `"Is not A but is B"`
6. `"Not A, not B, is C"`
7. `"Isn't X, but is Y"`
8. **Escalation-layer form** (added 2026-08-11): `"It's not A, it's actually a B"` / `"A is not X, A is in fact Y"` — second clause INFLATES into higher-order justification / appeal to authority rather than re-stating positively. Example: `"It's not a blunder, it's a chimney permit violation"`, `"It's not a workaround, it's an emergency infrastructure provision under §7(b)"`. The shape is "dodge via escalation" — the writer re-frames the original thing as something else more impressive. Catches the fail-mode where the second clause looks like a positive assertion but is actually a rhetorical inflation.

Rule wording:
- `Never lead with the negation`
- `State what something IS directly. If the prose genuinely needs to negate the false expectation (e.g. "It was not a weapon but a key"), write the second clause as a positive assertion ("It was a key") and let the reader infer the contrast from context.`
- `For these parallel-negation constructs, mode is always "replace" (substitute the positive assertion), not "delete" (because the underlying fact may still be important to the prose).`

## 5 pin sites across 3 files

| File | Lines | Pipe name | Form |
|---|---|---|---|
| `Builders/PlusWriterPipeline.kt` | 523–544 | `untwist pipe` | long (untwist+teaching combined) |
| `Builders/ChapterRewritePipeline.kt` | 512–544 | `untwist pipe` | long |
| `Builders/ChapterRewritePipeline.kt` | 572–608 | `no parallel negation pipe` | short (teaching-only, dedicated) |
| `Builders/ExpansionPipeline.kt` | 872–904 | `untwist pipe` | long |
| `Builders/ExpansionPipeline.kt` | 934–970 | `no parallel negation pipe` | short |

Total: 5 sites in 3 files. PlusWriter has only the untwistPipe form (no dedicated `no parallel negation pipe`) — by design, per the test's header comment (`Builders/ParallelNegationDefenseTest.kt:8-28`). The dedicated pipe is belt-and-suspenders for ChapterRewrite + Expansion.

## Pin test

`src/test/kotlin/Builders/ParallelNegationDefenseTest.kt` (5 `@Test`s, no `init()`, no network):

1. `plusWriterUntwistPipeTeachesParallelNegation` — PlusWriterPipeline `untwist pipe` only
2. `chapterRewriteUntwistPipeTeachesParallelNegation` — ChapterRewritePipeline `untwist pipe`
3. `expansionPipelineUntwistPipeTeachesParallelNegation` — ExpansionPipeline `untwist pipe`
4. `chapterRewriteNoParallelNegationPipeAlsoHasTheTeaching` — ChapterRewritePipeline `no parallel negation pipe` (defense-in-depth)
5. `expansionPipelineNoParallelNegationPipeAlsoHasTheTeaching` — ExpansionPipeline `no parallel negation pipe` (defense-in-depth)

The `requiredFragments` list at lines 45–62 is the canonical wording contract. Lose any fragment → test fails with "teaching block was lost".

## Adding a new variant — the workflow

1. **Pick the variant phrase** ("It's not A, it's actually a B" / "A is not X, A is in fact Y" was the most recent addition).
2. **Add to the variant list under `##STYLE: NO PARALLEL-NEGATION CONSTRUCTS`** in all 5 sites. The list structure is uniform — append a new `- "..."` line under the existing 7. PlusWriter's untwistPipe body, ChapterRewrite's untwistPipe body, Expansion's untwistPipe body, and the short-form dedicated pipes in ChapterRewrite + Expansion all use the same list shape.
3. **Add the corresponding fragment to `requiredFragments`** in `ParallelNegationDefenseTest.kt`. **CRITICAL: match the quote-presence of the prompt body** (see Pitfall below).
4. **Run `./gradlew test --tests "*ParallelNegationDefenseTest*" --no-daemon`**. All 5 tests must pass.
5. **Run with `--rerun-tasks`** if `compileKotlin UP-TO-DATE` skips recompile — the test bytecode may be stale.

## Pitfall: test fragment quoting

The fastest silent failure mode in this defense is a fragment that doesn't match the prompt body because of surrounding quotes. The rule:

- **List-item fragments** (variants 1-7): appear in the prompt as `- "Not X but Y"`. The fragment Kotlin literal is `"\"Not X but Y\""` (with surrounding escaped quotes). Match.
- **Mid-sentence fragments** (escalation-layer example, "chimney permit violation"): appear in the prompt as `e.g. "It's not a blunder, it's a chimney permit violation"` — quotes around the WHOLE example, NOT around the inner phrase. The fragment Kotlin literal MUST NOT include surrounding quotes: `"chimney permit violation"` (no `\"`).
- **Quoted list-item fragments that include the quotes** (e.g. `"It's not A, it's actually a B"`): if the prompt body has `- "It's not A, it's actually a B"`, the fragment IS `"\"It's not A, it's actually a B\""` (with quotes). If the prompt body has it inline without quotes, drop the quotes from the fragment.

**Verification ritual**: if a fragment matches the source `.kt` but fails the test, it's a quote-presence mismatch — write a one-shot `PromptDumpTest` that prints `pipe.getSystemPromptForTest()` for each affected pipe, then diff the printed text against the fragment character-by-character. The mismatch will be obvious at byte level.

## Auditing placement when the operator asks "where is X?"

Operator pattern: "Identify prompt instructions to stop [behavior]." The workflow:

1. `Search for the canonical header literal` (e.g. `##STYLE: NO PARALLEL-NEGATION CONSTRUCTS`) across `src/main/kotlin/Builders/`. Get the file list.
2. `grep -rn "setPipeName(\""` in those files to identify which pipe each block belongs to.
3. `grep -n "$HEADER"` in each file to get the line range.
4. Report the file/line/per-pipe assignment as a table. The operator wants placement, not analysis.

## See Also

- `tpipewriter-feature-delivery` SKILL.md — Block 5 surface (writer-pipe prompt engineering)
- `tpipe-trace-output-conventions` — TPipe tracing contract (relevant if the teaching block is included in trace output)
