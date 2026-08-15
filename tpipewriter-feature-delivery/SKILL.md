---
name: tpipewriter-feature-delivery
description: Class-level umbrella for shipping features into the TPipeWriter TUI/CLI writing app (com.example.tpipewriter). Loaded for any feature request that touches SlashCommand dispatch, Env.* mirror fields, TPipeSettings schema, ChapterMetadata snapshots, GuideSubshell save/load parity, the /help text, or settings.json persistence. Captures the multi-surface nature of every TPipeWriter feature (4 sinks per new setting — Env mirror field, TPipeSettings field, /subshell dispatch, /help line) and the TDD discipline for adding each. Reference recipes for compile-time verification under the sandbox-killed Gradle daemon. Use when adding a new slash command, adding a new runtime-overridable variable, adding a new TPipeSettings field, adding a new ChapterMetadata snapshot, auditing an existing feature for help/settings/dispatch completeness, or locating/auditing a pipeline builder's system-prompt teaching block (the Block 5 surface below).
version: 1.0.0
author: Ten Trillion Triangles LLC
license: MIT
created: 2026-06-26
tags: [tpipewriter, tpipe, kotlin, tdd, slash-command, settings.json, tuis, wiz]
metadata:
  hermes:
    tags: [tpipewriter, feature-delivery, kotlin, tdd, tui, cli]
---

# TPipeWriter Feature Delivery

TPipeWriter is the user-facing writing app at `/home/cage/Desktop/Workspaces/TPipeWriter/`. It's built on TPipe master (`/home/cage/Desktop/Workspaces/TPipe/TPipe/`, composite build via `includeBuild("../TPipe/TPipe")` per `settings.gradle.kts:1-4`). Every feature in TPipeWriter ships into FOUR surfaces at once. Missing any one of them produces a "broken in a quiet way" bug that the user notices later. This umbrella is the class-level playbook for not missing any.

## The 4-surface rule

When adding ANY new setting, variable, command, or feature to TPipeWriter, the implementation MUST touch all four surfaces. Missing one is a regression class — bugs from prior sessions have included "help says nothing about this command," "setting saves but doesn't restore on load," "command works but `/help` lists it as unknown."

### Surface 1: Env mirror field (in-process state)
**Location**: `src/main/kotlin/Globals/Env.kt` — `object Env`.

**Convention**: TPipeWriter uses an "active mirror" pattern. For each persisted setting there are TWO fields:
- The consumer-side field the pipeline reads (e.g. `Env.authorPrompt`, `Env.editorPrompt`, `Env.richardTreadwell`).
- The mirror field with `active` prefix (e.g. `Env.activeAuthorGuide`, `Env.activeEditorGuide`, `Env.activeRichardTreadwell`) that the persistence path writes so the consumer field and the saved file stay in sync.

If you're adding a new personality variable:
```kotlin
/**
 * Current <name> loaded into memory. Mirrors TPipeSettings.<name> on the
 * persistence side so the in-process prompt survives a process restart
 * without going through the file-on-disk load path.
 */
var active<Name> = ""
```
If you don't add the mirror, `saveSettings(...)` will update the file but the pipeline reads from the unmirrored field — drift bug.

### Surface 2: TPipeSettings field (persisted schema)
**Location**: `src/main/kotlin/Shell/Shell.kt:1081` — `data class TPipeSettings(...)`.

Add the field with a `= ""` (or `= 0` / `= false`) default so old `~/.TPipeWriter/settings.json` files deserialize without the field present. TPipe's `coerceInputValues = true` honors Kotlin defaults on missing JSON fields — see `tpipe-json-serialization` skill.

```kotlin
@kotlinx.serialization.Serializable
data class TPipeSettings(
    var writingStyle: String = "",
    // ... existing fields ...
    var editorGuide: String = "",  // <-- new field, default empty
    var <newField>: <Type> = <default>
)
```

**Test it**: write a `TPipeSettingsTest` (or extend existing) with a JSON literal that omits the new field and assert the deserialized object has the default value. Backward-compat test pattern from `src/test/kotlin/Shell/TPipeSettingsTest.kt:oldSettingsJsonWithoutEditorGuideDeserializesWithEmptyDefault`.

### Surface 3: SlashCommand dispatch
**Location**: `src/main/kotlin/Shell/Shell.kt` — the `when(extractedSlashCommand)` block around line 282.

```kotlin
            "<newCommand>" -> <newEntryPoint>()
```
The command string is the entry-point WITHOUT a leading `/`. The entry-point function returns `Unit` and is usually a subshell loop (mirror the existing `/guide`, `/author`, `/editor` subshells in `Shell/` and `GuideSubshell.kt`).

**Subshell pattern**: If the new command needs user-driven sub-flows (save / load / edit), mirror the `/editor` subshell — `selectXxxMode()` loop with `parseXxxCommand(rawInput)` pure parser + `XxxCommand` enum. Unit-test the parser exhaustively.

### Surface 4: `/help` text
**Location**: `src/main/kotlin/Shell/Shell.kt:1236` — `fun printHelp()`.

Every accepted slash command MUST appear in the help text. TDD: write `Shell.<X>HelpTest` that captures `System.out` during `printHelp()` and asserts the command name appears. Then add the line.

Existing help text format (each line: `|<cmdPad> - <description>`):
```kotlin
        |/editor            - Open the editor-personality menu (save/load editor guide)
        |/budget-info       - Print the token budget applied to every writer pipe
```

### Surface 5 (inspector commands): reading from a top-level constant
**Pattern**: Some slash commands don't manage user state — they *inspect* immutable policy surfaces applied elsewhere in the codebase. Example: `/budget-info` reads `Builders.plusWriterPipelineBudget` (a top-level `val` in `PlusWriterPipeline.kt`) and prints its values.

For these commands, the surfaces that do NOT apply are **1, 2, 3-as-save-load, 5a**:
- **No `Env.*` field**: nothing to mirror in process state. The source of truth lives in `Builders/` or wherever the constant is defined.
- **No `TPipeSettings` field**: nothing to persist. The value is a build-time policy.
- **No subshell**: `/budget-info` is read-only and synchronous.
- **No ChapterMetadata snapshot**: not per-chapter data.

What DOES apply:
- **SlashCommand dispatch entry** (the `when(extractedSlashCommand)` line).
- **`/help` line** that describes the command.
- **The implementation function** (e.g. `printBudgetInfo()`) which **imports** the source-of-truth constant from another module and prints it verbatim. Don't re-derive; don't re-instantiate; don't read from a running pipeline (it may not exist). Import the constant.
- **Two tests**: `HelpTest` (asserts `/help` mentions the command) + a runtime smoke test under tmux that captures the printed output.

**Why this is its own surface**: a future session will look at `/budget-info` and ask "where's the Env mirror? where's the TPipeSettings field?" — and try to add them. That adds drift for no value. Document the 5th surface as "the constant lives in `Builders/<X>.kt`, the command imports it, full stop."

**Inspector commands GROW over time as posture surfaces are added.** When a new policy is wired in `Builders/PlusWriterPipeline.kt` (e.g. `useEntireContextForLoreSelection()` flipped on alongside `setTokenBudget()`), extend the existing inspector command's print block instead of spawning `/lore-scan-info` or `/context-policy-info`. The pattern is "one inspector command per pipeline posture report." This keeps `/help` short, gives the user a single command to verify everything, and avoids a sprawl of `/X-info` commands that all read from the same builder file.

Reference: `src/main/kotlin/Shell/Shell.kt` lines 1267-1290 — `fun printBudgetInfo()` definition (currently surfaces token budget + lorebook scan posture; add new sections here when new posture surfaces are wired in the builder).

## Per-pipe wire-up in builders — the post-init apply-block pattern

When a posture (token budget, lorebook scan surface, future policies) must apply to **every pipe** in a pipeline, do not add per-pipe calls at the construction sites. Instead, define the posture as a top-level `val` in `Builders/<Pipeline>.kt` and apply it via the existing post-init `.apply { getPipes().forEach { ... } }` block at the tail of the pipeline builder function. The block already exists in `PlusWriterPipeline.kt:1554-1559` for `setTokenBudget()` + `enableComprehensiveTokenTracking()` — add to it, don't create a new one.

```kotlin
return plusWriterPipeline.apply {
    getPipes().forEach {
        it.useEntireContextForLoreSelection()    // <-- new posture, same forEach
        it.setTokenBudget(plusWriterPipelineBudget)
        it.enableComprehensiveTokenTracking()
    }
    // ...
}
```

**Order matters**: lorebook scan surface first, then budget, then tracking. Rationale: scan surface is a per-pipe setting that affects every call site; budget depends on context window size; tracking observes everything. Earlier in the forEach = wires the policy before the executor reads it.

**TDD shape**: write a test that calls `buildPlusWriterPipeline()` and asserts `pipe.toPipeSettings().<newPosture>` (or the equivalent accessor) on every pipe. Pair with helper-level tests that pin the underlying behavior contract independently — the helper test passes before the wire-up (it tests the framework), the per-pipe test fails RED for the right reason ("Pipe 'X' must have <newPosture> = true") and turns GREEN after the wire-up.

**Pitfalls** discovered during wire-up:
- `pipe.toPipeSettings()` is the settings accessor, NOT `getPipeSettings()` — only `toPipeSettings()` exists on `Pipe`. Compile error otherwise.
- `ConverseRole` lives in `com.TTT.Context`, NOT `com.TTT.Pipe`. Use `import com.TTT.Context.ConverseRole` in test code.
- When defining a top-level constant alongside the apply-block, keep it in the same file (`Builders/<Pipeline>.kt`) so the inspector command can `import Builders.<name>` without a cross-module dependency.

## Lorebook scan surface posture — `useEntireContextForLoreSelection()`

When wiring per-pipe policies, the **lorebook scan surface** is the most commonly missed posture after token budget. The default scans only the user prompt; lorebook entries whose keys reference concepts in `contextElements` or `converseHistory` will not match unless this is flipped on. See `tpipe-token-budgeting` (Lorebook selection surface section) for the full contract — the TL;DR for the PlusWriterPipeline pattern is "if you're porting the Autogenesis lorebook-as-overflow pattern, set `useEntireContextForLoreSelection()` on every pipe in the same forEach as `setTokenBudget()`."

---

## System-prompt teaching blocks — the Block 5 surface (writer-pipe prompt engineering)

Writers/transformers in `Builders/*Pipeline.kt` carry `.setSystemPrompt("""...""")` calls that inject teaching blocks into the LLM. These are a fifth surface parallel to the four runtime surfaces above — they pin *generation behavior* rather than *feature persistence*, and they have their own test pattern.

**Canonical example: the parallel-negation defense.** Whenever the LLM is rewinding or rewriting prose, the model default-draws toward "not X but Y" / "it's not X, it's Y" as a cheap-contrast device. The project mitigates this with a teaching block whose canonical header is the literal `##STYLE: NO PARALLEL-NEGATION CONSTRUCTS`. The block lists 8 variant constructs (Not X but Y, It's not X it's Y, Not because A but because B, Not A but B, Is not A but is B, Not A not B is C, Isn't X but is Y, **and the escalation-layer form: "It's not A, it's actually a B" / "A is not X, A is in fact Y"** — second clause INFLATES into higher-order justification / appeal to authority rather than re-stating positively) and pins `mode is always "replace"` for the surgical rewrite, plus the positive-assertion rule `Never lead with the negation`.

**5 pin sites across 3 files** (verified layout, do not edit without updating the test):

| File | Lines | Pipe name |
|---|---|---|
| `src/main/kotlin/Builders/PlusWriterPipeline.kt` | 523–544 | `untwist pipe` (only; no dedicated `no parallel negation pipe`) |
| `src/main/kotlin/Builders/ChapterRewritePipeline.kt` | 512–544 | `untwist pipe` |
| `src/main/kotlin/Builders/ChapterRewritePipeline.kt` | 572–608 | `no parallel negation pipe` |
| `src/main/kotlin/Builders/ExpansionPipeline.kt` | 872–904 | `untwist pipe` |
| `src/main/kotlin/Builders/ExpansionPipeline.kt` | 934–970 | `no parallel negation pipe` |

**Pinned by** `src/test/kotlin/Builders/ParallelNegationDefenseTest.kt` (5 `@Test`s, no network, asserts on `getSystemPromptForTest()` substrings). The `requiredFragments` list at lines 45–62 is the canonical wording contract — losing any one fragment degrades the defense. The test also asserts defense-in-depth at lines 109–147: the dedicated `no parallel negation pipe` must carry the same teaching block, so if someone unhooks the dedicated pipe the test fails loudly and points the user back to the untwistPipe-only fallback.

**Why PlusWriter has only the untwistPipe form**: by design, per the test's header comment (lines 8–28). untwistPipe covers the "it's not X, it's Y" overlap; the dedicated `no parallel negation pipe` in ChapterRewrite + Expansion is a belt-and-suspenders addition, not a PlusWriter gap.

**TDD pattern for any new teaching block**: define a constant or template for the block header text, write `Builders/<X>TeachingBlockTest.kt` that builds the pipeline (no `init()`, no network) and asserts `pipe.getSystemPromptForTest().contains(headerLiteral)` + each load-bearing fragment. The `getSystemPromptForTest()` accessor lives on the pipe and is the safe way to expose the system prompt for tests without leaking the full `Pipe` API.

**When adding a new teaching block to a pipe**: locate the pipe's `setSystemPrompt("""...""")` call, append the block under a `##STYLE: <NAME>` header, then add a fragment-presence test. If the new block crosses pipes (e.g. a shared "no ai-slop" rule that needs both untwistPipe and a new aiSlopPipe), add the test across all sites — same contract everywhere.

**When auditing an existing teacher block** (the operator pattern: "where is the prompt that prevents X?"): grep for the canonical header literal across `src/main/kotlin/Builders/`, then `grep -n "setPipeName(" in the same file to identify the pipe each block belongs to. Done. The user wants the placement, not a treatise.

## The "completeness audit" checklist

When reviewing an existing feature for completeness (the user's pattern: "is there a setting for X?"), check ALL of:

1. **Env field** exists? Is there a consumer field AND a mirror field?
2. **TPipeSettings field** exists with default? Backward-compat test passes?
3. **SlashCommand dispatch** routes the command to a working function?
4. **`/help`** mentions the command?
5. **settings.json** write path persists the value?
6. **ChapterMetadata snapshot** (if it's a per-story personality) — field exists with default?
7. **`/author` or `/editor` subshell** can save/load it?
8. **live `~/.TPipeWriter/settings.json`** shows the field populated after a save?

If the user asks "where's the setting for X" and the answer is "it's hard-coded in source" — that's a feature gap, not a missing implementation.

## Settings → runtime binding verification pattern (NEW 2026-08-13)

When adding a new feature that **flows a value from disk into a long-lived runtime object the user actually drives** (a `Pipe`, a `Pipeline`, a per-pipeline `ReasoningSettings.roleCharacter`, an `Env.*` field that pipes snapshot at build time), the unit-test surface is NOT just "the helper updates the in-memory field." The in-memory field is the agent's local view; the **runtime object the user operates is downstream**. A unit test that only inspects the helper's field will pass green while the feature is broken at the user-facing surface.

**The load-bearing test shape for any settings → runtime binding feature:**

1. **Write a fixture to disk** with the binding value under test (e.g.
   `TPipeSettings(personalityRoster = …, personalitySlotBindings = …)`
   serialized to `~/.TPipeWriter/settings.json`).
2. **Call the production code path** the same way the TUI does — not a
   parallel implementation. For settings, that's typically the
   `applyPersonalitySlotsFromSettings()` helper that `Env.init` calls
   at the top of its body, plus the `rebindPersonalitySlotsAndRebuildPipelines()`
   helper that the TUI's assign-slot path calls.
3. **Inspect the runtime object the user actually drives**, not just
   the in-memory helper field. For personality bindings, walk
   `Env.plusWriterPipe.getPipes()` and verify the body the user picked
   is reachable in `pipe.toPipeSettings().systemPrompt`. For other
   features, the equivalent probe is whatever the user clicks/types
   to see the binding take effect.
4. **Use a unique probe phrase** in the body that no other seeded
   personality contains (e.g. `"ZZZ_PROBE_<topic>"`). The probe lets
   the assert prove the exact body landed, not "some body that looks
   like ours."

**Worked example from the 2026-08-13 personality feature session:**
the user reported "agents behave with the old personalities so that
setting does not take when bound." The unit test on the helper
(`applyPersonalityBindings` writes `Env.authorPrompt`) was green, but
the runtime pipe still carried the OLD body because the pipe snapshotted
`Env.authorPrompt` at `buildPlusWriterPipeline()` construction time. The
fix was TUI-side: `assignPersonalityToSlot` calls `rebindPersonalitySlotsAndRebuildPipelines()`
which re-runs `Env.init` so the pipe rebuilds against the new value. The
test that caught this regression walked `Env.plusWriterPipe.getPipes()`
and read `pipe.toPipeSettings().systemPrompt` — the surface the user
actually sees the LLM write in.

**Recipe for the test:**

```kotlin
@Test
fun bindingFlowsFromEnvFieldsIntoRunningPipeSystemPrompt() {
    // Skip if the wire layer requires an API key that the CI doesn't have.
    val key = System.getenv("MINIMAX_API_KEY")
    assumeTrue(!key.isNullOrBlank(),
        "MINIMAX_API_KEY is not set; this test rebuilds real pipes.")

    val body = """You are Probe Author. ZZZ_PROBE_universe-pear marker."""
    val settings = TPipeSettings(
        personalityRoster = roster + ("Probe Author" to body),
        personalitySlotBindings = mapOf(AuthorSlot.AUTHOR_PROMPT.name to "Probe Author", ...)
    )
    installSettings(settings)  // writes ~/.TPipeWriter/settings.json

    applyPersonalitySlotsFromSettings()  // phase 1
    rebindPersonalitySlotsAndRebuildPipelines()  // phase 2 (rebuilds pipes)

    // Phase 3: assert at the runtime surface the user actually drives.
    val probeHit = Env.plusWriterPipe.getPipes()
        .firstOrNull { pipe ->
            (pipe.toPipeSettings().systemPrompt ?: "").contains("ZZZ_PROBE")
        }
    assertNotNull(probeHit,
        "Pipeline rebuilt, but no pipe carried the probe body. The binding isn't reaching the running pipes.")
}
```

**Why this test shape works:**
- The `assumeTrue(::MINIMAX_API_KEY)` guard lets the test run in CI
  without a wire and SKIP cleanly (not silently pass). When the wire
  is available, the test fires for real and the assertions are
  load-bearing.
- The walk through `getPipes()` is the same walk the user does
  implicitly when they `/write` and observe the LLM's output. If the
  walk here can't find the probe, the walk in production can't
  either.
- The probe phrase is in the test code, not the production code. It
  doesn't pollute the user-facing feature.

**Anti-patterns to avoid:**

- **"I assert that Env.authorPrompt equals the new body, that's enough."** —
  `Env.authorPrompt` is the source, not the sink. The sink is the
  pipe's `pipeSettings.systemPrompt` or `reasoningSettings.roleCharacter`.
  Asserting on the source alone missed the bug the user reported.
- **"I assert on `pipe.toPipeSettings().systemPrompt` contains the
  binding, that's enough."** — the surrounding code may still have
  the wrong behavior (e.g. a string interpolation that didn't pick up
  the new value). The unique-probe phrase is the cheapest way to
  distinguish a real wiring from a placeholder.
- **"I'll spy on the writer pipeline directly and skip the wire
  rebuild."** — a unit test that calls `applyPersonalityBindings`
  without `Env.init` (or `rebindPersonalitySlotsAndRebuildPipelines`)
  is testing the helper, not the wiring. The user reported the wiring
  was broken; the helper can be 100% correct and the wiring still be
  broken.

**Companion to the existing TUI verification discipline.** The
`references/tui-verification-discipline.md` neighbor covers the broader
"drive every command, parse the trace, check disk artifacts" rule for
shipping a TUI feature. This section is the load-bearing test shape
specifically for settings-into-runtime-data flows. Both are required;
they check different failure surfaces.

## Settings-file merge vs overwrite on load (NEW 2026-08-13)

When a TUI action reads `~/.TPipeWriter/<​filename>-settings.json` and
applies it to the global `~/.TPipeWriter/settings.json`, the default
should be **merge, not overwrite**. The anti-pattern is
`saveSettings(loadedSettings)` at the top of the load body — this
silently erases any TPipeSettings field that the per-story file does
NOT contain. Legacy per-story files exported before a new feature
shipped have no field for the new feature; overwriting the global with
that legacy data drops the user's current binding for the new feature.

**Pattern: read global first, merge per-story fields, save the merged
result, then init.**

```kotlin
val globalBefore = loadSettings()
val merged = loadedSettings.copy(
    personalityRoster = loadedSettings.personalityRoster
        .ifEmpty { globalBefore.personalityRoster },
    personalitySlotBindings = loadedSettings.personalitySlotBindings
        .ifEmpty { globalBefore.personalitySlotBindings }
)
saveSettings(merged)
Env.init(merged.writingStyle, merged.temperature, merged.topP, merged.maxTokens, merged.useAutoLorebook)
```

**Why this works for backward compatibility:**
- New per-story file (exported with the binding) → `personalityRoster`
  is non-empty → `loadedSettings.personalityRoster` wins, the global
  binding is replaced. The user picked up the story's binding.
- Legacy per-story file (exported before the binding feature) →
  `personalityRoster` is empty → falls back to `globalBefore.personalityRoster`.
  The user's current binding is preserved.
- Partial per-story file (binding present for some slots only) →
  the per-story file wins for the slots it has, the global file wins
  for the slots it doesn't. Slot-by-slot merge.

**Test classes that pin this contract:**
- `Shell.PersonalityExportLoadRoundTripTest.legacySidecarWithoutBindingPreservesGlobalBinding`
  — legacy file → global binding survives.
- `Shell.PersonalityExportLoadRoundTripTest.perStoryBindingPartiallyPresentMergesSlotBySlot`
  — partial file → slot-by-slot merge.
- `Shell.PersonalityExportLoadRoundTripTest.loadAppliesBindingFromSidecarWhenPresent`
  — full file → per-story binding wins.

**Anti-patterns:**

- `saveSettings(loadedSettings)` at the top of the load body — wholesale
  overwrite, silent loss of any field the legacy file doesn't have.
- `if (loadedSettings.<field>.isNotEmpty()) <mutate>; else <keep global>`
  per field — works but verbose. The `.copy(...).ifEmpty { ... }` chain
  is shorter and keeps the merge logic visible in one place.
- Assuming the per-story file and the global file are "the same
  schema" — they're not. The per-story file is a snapshot at export
  time; the global file is the user's current state. Merge, don't
  replace.

## Chapter-snapshot vs settings-binding coexistence (NEW 2026-08-13)

TPipeWriter has TWO mechanisms for capturing per-story personality state:

1. **ChapterMetadata snapshot** (older): `authorPromptSnapshot`,
   `editorPromptSnapshot`, `richardTreadwellSnapshot` fields on
   `Chapter.ChapterMetadata`. Captured at `exportStory` time by
   `Chapter.capturePersonalitySnapshot(...)`; restored at `loadStory`
   time by `Chapter.applyPersonalitySnapshot(...)`. The snapshot is
   per-chapter and per-personality.
2. **TPipeSettings.personalitySlotBindings** (newer): a `Map<String, String>`
   where keys are `AuthorSlot` enum names and values are roster names.
   Persisted in `~/.TPipeWriter/settings.json` and the per-story
   `<​filename>-settings.json`. The binding is per-trait and persists
   across the whole project.

**When both exist on a loaded story, the settings binding wins.** The
`loadStory` order is:

1. `<​filename>-story.json` parsed → chapter metadata applied via
   `Chapter.GlobalChapterManager.loadMetadata(...)`.
2. First chapter with a non-empty snapshot → `applyPersonalitySnapshot(...)`
   writes `Env.authorPrompt / editorPrompt / richardTreadwell` from
   the snapshot.
3. `<​filename>-settings.json` parsed → merge with global settings → `saveSettings(merged)`
   → `Env.init(...)` runs → at the top of `Env.init`,
   `applyPersonalitySlotsFromSettings()` reads the just-written
   `~/.TPipeWriter/settings.json` and writes ALL FOUR Env.* fields from
   the slot bindings.

The chapter-snapshot is overridden by the settings binding because
step 3 runs after step 2. The chapter-snapshot is preserved in the
chapter metadata but does not pollute the live `Env.*` fields after
load completes.

**Pinned by `Shell.PersonalityExportLoadRoundTripTest.chapterSnapshotAndSettingsBindingCoexist`:
the test constructs a story with both an older chapter-snapshot AND
a settings binding, runs the load body, and asserts that the
settings binding's body is what `Env.authorPrompt` ends up holding
(NOT the chapter-snapshot's body).

**Test fixture shape:**

```kotlin
val chapterMetadata = mapOf(
    0 to ChapterMetadata(
        authorPromptSnapshot = "Chapter Snapshot Author body.",
        // ...
    )
)
val storyBindings = mapOf(
    AuthorSlot.AUTHOR_PROMPT.name to "Settings Author",
    // ...
)
val loadedSettings = TPipeSettings(
    personalityRoster = settingsRoster,
    personalitySlotBindings = storyBindings
)
// Phase A: chapter-snapshot restore (legacy path).
val (newAuthor, _, _) = Chapter.applyPersonalitySnapshot(
    metadata = chapterMetadata.values.first(),
    currentAuthorPrompt = Env.authorPrompt, ...
)
Env.authorPrompt = newAuthor
// Phase B: settings merge + bind.
val merged = loadedSettings.copy(
    personalityRoster = loadedSettings.personalityRoster.ifEmpty { globalBefore.personalityRoster },
    personalitySlotBindings = loadedSettings.personalitySlotBindings.ifEmpty { globalBefore.personalitySlotBindings },
)
saveSettings(merged)
applyPersonalitySlotsFromSettings()
// Assert: settings binding wins, chapter-snapshot is overridden.
assertEquals(settingsBody, Env.authorPrompt)
assertFalse(Env.authorPrompt.contains("Chapter Snapshot Author"))
```

**Anti-patterns:**
- Re-ordering the load body so the chapter-snapshot restore runs AFTER
  the settings merge — that would silently let older stories keep
  their on-disk-snapshot personas instead of the user's current
  binding. The settings binding is the source of truth on load.
- Dropping the chapter-snapshot restore path entirely — the snapshot
  is preserved in chapter metadata and may be useful for future
  features (e.g. a per-chapter auto-snapshot toggle). Don't prune
  the capture helper; just stop relying on it as the persistence
  source.

---

## TDD discipline (TPipeWriter-specific)

Every TPipeWriter feature follows RED-GREEN-REFACTOR.

### RED pattern
```kotlin
@Test
fun <feature>() {
    // capture stdout if testing printHelp or other console output
    val out = java.io.ByteArrayOutputStream()
    val original = System.out
    System.setOut(java.io.PrintStream(out))
    try { <thing>() } finally { System.setOut(original) }
    assertTrue(out.toString().contains("<expected>"))
}
```

### Interactive-path test (the one pattern the user explicitly trusts)
TPipeWriter has interactive functions that read stdin via `readEnhancedInput()` (from TPipe master) and `readln()` (from Kotlin stdlib). To unit-test them end-to-end:

```kotlin
@Test
fun interactivePath() {
    if (System.console() != null && !isAttyOverridden()) {
        // Real TTY — readln() won't see piped bytes; skip the test.
        return
    }
    val joined = "<content>\n<name>\n"
    System.setIn(ByteArrayInputStream(joined.toByteArray(Charsets.UTF_8)))
    saveXxx()
    assertEquals("<content>", Env.xxxPrompt)
    // ... etc
}
```
Reference: `src/test/kotlin/Shell/GuideSubshellRegressionTest.kt`. Pattern works because under gradle the JVM has no TTY, so `System.console()` returns null and Kotlin's `readln()` falls back to `System.in`.

### Compile-and-test under the sandbox
The sandbox kills Gradle daemons mid-build. Use the constrained recipe:
```bash
JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" \
./gradlew test --console=plain --no-daemon --offline
```
First run takes 2-4 minutes. If gradle still fails, bypass with `kotlinc` directly + JUnit Platform launcher shim — see `references/gradle-plan-author-pitfalls.md` Pitfalls 6+7 in the interactive-plan skill. For the TPipe main module specifically, when gradle is blocked on TPipe-MCP transitive deps (a known sandbox limitation), use the **stub-bypass pattern** to verify new @JvmStatic entry points on `NativeBridge.kt` without needing `./gradlew nativeCompile`. See `references/abi-stub-bypass.md` for the full recipe + the 6 pitfalls that surface in practice.

**Pitfall (user-corrected 2026-07-12)**: Do NOT claim a `NativeBridge.kt` line "doesn't compile" because a standalone `kotlinc` against the cached compiled main reported `cannot access 'fun ensureJsonPromptInjectionEnabled()': it is internal in 'Pipe'`. The line compiles fine under `./gradlew :compileKotlin` (which honors module-internal visibility). The standalone kotlinc invocation doesn't carry module-metadata across compilation units. Cross-package `internal` requires gradle's friend-path resolution; direct kotlinc treats it as opaque and reports a misleading "internal" error. Verify with gradle before declaring any line broken; standalone kotlinc alone is not ground truth for `internal` access violations.

---

## Verification chain

After every TPipeWriter feature delivery:

1. **`./gradlew test`** — full unit suite must remain green. Count grows monotonically; new feature adds new tests.
2. **tmux end-to-end** — launch the installed dist under tmux, drive the new slash command, capture the screen, assert no framework errors in the captured output.
3. **`~/.TPipeWriter/settings.json`** — confirm the new field persists round-trip (save → reload → assert equality).
4. **`/help`** — confirm the new command is listed.

The user's verification rule: "spot-checking TUI commands is not enough; drive every command via tmux and parse the trace afterward." For TPipeWriter that translates to: drive the new slash command end-to-end through the real shell, not just via unit tests of the parser.

---

## Common anti-patterns (TPipeWriter-specific)

| Anti-pattern | Why it bites | Fix |
|---|---|---|
| Adding only the Env field without TPipeSettings | Save loses the value; reload returns default | Add both. TPipeSettings default must be safe. |
| Adding the slash command without `/help` | User can't discover the command | Add `/help` line. TDD it. |
| Adding subshell save/load without Env mirror | Save updates file but live process doesn't reflect change | Mirror via `Env.active<Name>`. |
| Using `: Boolean = false` for TPipeSettings discriminator fields | TPipe's `encodedefault = false` (post-2026-06-22) drops discriminator fields; MiniMax rejects missing `type` discriminator. | Use `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` or set the default value explicitly at the call site. See `tpipe-json-serialization` skill pitfall. |
| Reading-only `~/.TPipeWriter/settings.json` in tests via direct file read | Tests are flaky if HOME isn't overridden | Set `System.setProperty("user.home", tempDir.toAbsolutePath().toString())` in `@BeforeEach` and restore in `@AfterEach`. |
| Running `System.out.println` in test code without capturing | Test pass/fail doesn't reflect the printed content | Capture via `ByteArrayOutputStream` + `System.setOut`. |
| Skipping live tmux verification | Some bugs only surface in the real shell (streaming buffering, dispatch routing, settings persistence) | Drive every new command via tmux + capture screen. |
| Using `System.setProperty("MINIMAX_API_KEY", ...)` in tests to satisfy GenericOpenAI pipes | `GenericOpenAIEnv.resolveApiKey()` does NOT see system properties — only the explicit `setApiKey(...)` setter and the env-var fallback `getApiKeyFromEnv()`. Tests will fail with `IllegalStateException: GenericOpenAI API key is required` even though the property is set. | Call `GenericOpenAIEnv.setApiKey("sk-test-fake-key")` directly in the test's `@BeforeAll` companion object. Package: `genericOpenAIPipe.env.GenericOpenAIEnv`. Do this ONCE per test class — the env holds a static field. |
| Forgetting that `--tests "ClassName"` filter doesn't pick up newly added test classes | Gradle re-runs only classes the filter matches by exact or substring pattern; new files created mid-session aren't auto-included. | Run unfiltered `./gradlew test --rerun-tasks` after adding a test class, then grep the XML report for the new class name to verify it ran. The `--rerun-tasks` flag forces execution; the unfiltered run guarantees discovery. |
| Lecturing when the operator asks "where is X?" | Operator voice: "Just learn about where it is." A multi-paragraph framed response to a placement question reads as overwritten. The operator wants file:line citations, not analysis. | Cite the file/line/per-pipe, give one line of categorical context, stop. If multiple reads are plausible, ask one disambiguating question, then commit. |
| **Writing prompt-substring test fragments with surrounding escaped quotes when the phrase appears mid-sentence in the prompt body** | The test `assertUntwistTeachesParallelNegation` asserts `systemPrompt.contains(fragment)` where fragments are Kotlin string literals. A fragment like `"\"chimney permit violation\""` evaluates to the runtime string `"chimney permit violation"` (with surrounding double-quotes). If the prompt body holds the phrase mid-sentence (e.g. `e.g. "It's not a blunder, it's a chimney permit violation"` — quotes around the whole example, NOT around the inner phrase), the fragment with quotes will NEVER match. The test fails with a misleading "teaching block was lost" assertion, even though the prompt body is correct. | When choosing a fragment for a teaching-block test, locate the phrase in the actual prompt body and copy the surrounding quotes-as-presented: mid-sentence fragments → no surrounding quotes in the fragment; quoted list-item fragments like `- "It's not X, it's Y"` → fragment DOES include surrounding quotes (`"\"It's not X, it's Y\""`). The fastest verification: write a `PromptDumpTest` that prints `pipe.getSystemPromptForTest()` for each affected pipe, then write the fragment against the dumped text character-by-character. If the fragment matches the source `.kt` string but fails the test, that's a quote-presence mismatch every time. **Code fact, not a per-edit issue**: the parallel-negation test's `requiredFragments` list uses MIXED quoting — most list-item fragments include the surrounding quotes (line 48-54), but the `chimney permit violation` fragment (line 56) does NOT. This is correct; future additions must follow the same audit. |
| **Asserting only on the in-memory helper field for a settings-into-runtime binding feature (NEW 2026-08-13)** | The unit test on `applyPersonalityBindings` writes `Env.authorPrompt = newBody` is green, but the runtime pipe still carries the OLD body because the pipe snapshotted `Env.authorPrompt` at `buildPlusWriterPipeline()` construction time. The user reports the binding "didn't take"; the test is green; the bug ships. | For any feature that flows a value from disk into a long-lived runtime object the user actually drives (a Pipe, a Pipeline, a per-pipeline `ReasoningSettings.roleCharacter`), the load-bearing test must inspect the runtime object — walk `pipeline.getPipes()`, read `pipe.toPipeSettings().systemPrompt`, assert the user-picked body is reachable there. See the "Settings → runtime binding verification pattern" section above for the full recipe. |
| **Wholesale overwrite of `~/.TPipeWriter/settings.json` on story load (NEW 2026-08-13)** | `loadStory` does `saveSettings(loadedSettings)` at the top of the load body, which writes the per-story file's contents over the global. A legacy per-story file (exported before a new TPipeSettings field existed) has empty defaults for that field; overwriting the global with the legacy data drops the user's current binding for the new feature. The user reports "my binding vanished when I loaded an old story." | Merge, don't overwrite. Read global first, then `loadedSettings.copy(personalityRoster = loadedSettings.personalityRoster.ifEmpty { globalBefore.personalityRoster }, ...)` for each empty-default field, then `saveSettings(merged)`. The `.ifEmpty { ... }` chain preserves the global binding when the per-story file has no entry. See the "Settings-file merge vs overwrite on load" section above for the full recipe. |

---

## File locations (quick reference)

| File | Role |
|---|---|
| `src/main/kotlin/Globals/Env.kt` | `object Env` — runtime state + mirror fields |
| `src/main/kotlin/Shell/Shell.kt` | `printHelp()`, slash-command dispatch, `TPipeSettings` data class, `loadSettings()`/`saveSettings()`, **inspector functions** like `printBudgetInfo()` |
| `src/main/kotlin/Shell/GuideSubshell.kt` | Save/load functions for guides, Richard Treadwell |
| `src/main/kotlin/Shell/EditorSubshell.kt` | `/editor` subshell loop + parser |
| `src/main/kotlin/Chapter/ChapterMetadata.kt` | Per-chapter snapshot fields + `capturePersonalitySnapshot()` / `applyPersonalitySnapshot()` pure helpers |
| `src/main/kotlin/Builders/PlusWriterPipeline.kt` | Writer pipeline builder, plus top-level `TokenBudgetSettings` constants (e.g. `plusWriterPipelineBudget`) used by inspector commands |
| `src/test/kotlin/Shell/PrintHelpTest.kt` | `/help` content contract |
| `src/test/kotlin/Shell/BudgetHelpTest.kt` | `/budget-info` + `/help` mentions-budget contract (the inspector-command test pattern) |
| `src/test/kotlin/Shell/GuideSubshellRegressionTest.kt` | Interactive save/load via stdin piping |
| `src/test/kotlin/Builders/ParallelNegationDefenseTest.kt` | Teaching-block placement contract — pins the `##STYLE: NO PARALLEL-NEGATION CONSTRUCTS` block across 5 sites. Reflective test, no network. |
| `references/parallel-negation-defense.md` | Pin-site table for the Block 5 surface, the 7 variant constructs, the `requiredFragments` contract, and the audit ritual for finding any other writer-pipe teaching block. |
| `docs/maestro/transcripts/<feature-slug>/` | Tmux end-to-end transcripts (one transcript per dispatch test) |
| `docs/maestro/reports/YYYY-MM-DD-<feature-slug>-report.md` | Final delivery report |

---

## See Also

- `tpipe-json-serialization` — `coerceInputValues` round-trip safety, `encodedefault` defaults, `@EncodeDefault` for discriminator fields
- `tpipe-pipeline-patterns` — TPipe pipe builder pattern, `setTokenBudget()` example
- `tpipe-token-budgeting` — TPipe `TokenBudgetSettings` primitive (separate skill, full deployment recipe)
- `tpipe-generic-openai` — MiniMax API quirks and provider surface
- `interactive-plan` — Plan workflow + sandbox verification recipe
- `references/persona-vs-skill-conflict.md` — when a persona is active alongside a loaded skill
- `references/plus-writer-per-pipe-wireup.md` — concrete 4-step recipe for wiring a new posture (token budget, lorebook scan surface, future policies) to every pipe in PlusWriterPipeline, with pitfalls and the audit checklist