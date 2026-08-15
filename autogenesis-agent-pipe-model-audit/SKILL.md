---
name: autogenesis-agent-pipe-model-audit
description: Audit which Bedrock models are wired into the Autogenesis TPipe agent pipe fleet and produce a fleet-wide scope covering both model migrations (e.g. qwen235B → qwenCoder30B) AND Bedrock service-tier routing — setServiceTier(BedrockPriorityTier.Flex) eligibility per pipe (cheap/async vs Standard). Classifies each occurrence as Main / Reasoning / Branch / Validator / Swap / Dead, traces which orchestrator invokes the builder, applies the "strict-simple output schema" filter for Flex eligibility, and produces a file:line scope table with a separate exclusion list. Use when migrating LLM models, scoping cost from pricing changes, marking pipes for Flex-tier routing, auditing every live call site of a model constant, reviewing a build<X>Agent factory against the canonical buildPassFailAgent factory-builder shape, or wiring DEV_SAFETY_LIVE_TEST-style dev-mode opt-in flags for safety pipelines. NOT for prompt-text debugging, trace analysis, single-pipe edits, or server-side smoke tests.
version: 1.3.0
author: Hermes Agent (extracted from qwen235B audit session 2026-07-25; extended with qwenCoder30B Flex eligibility audit 2026-07-25; extended with Gondwana pre-init + test-seam + diagnostic-fail-loudly sections 2026-08-10; extended with factory-builder + auto-ARN-resolution + ConfigSource property-vs-propertyOrEmpty + live-safety opt-in env-var + premature-completion discipline sections 2026-08-12)
created: 2026-07-25
updated: 2026-08-12
tags: [autogenesis, tpipe, bedrock, audit, migration, model-scope, agent-pipe, flex-tier, cost-optimization, factory-builder, dev-mode-bypass]
changelog:
  - 1.0.0 (2026-07-25): Initial extraction. Captures the pipe-slot taxonomy, 7-step audit methodology, 7 pitfalls, and 3 live orchestrator entry points.
  - 1.2.0 (2026-08-10): Four new sections derived from the Gondwana map-safety live-test session. (1) DITL pre-init hooks for content-rebuild in split-payload pipes. (2) The TPipe-blessed-serializer preference com.TTT.Util.serialize over Json.encodeToString. (3) Diagnostic-fail-loudly tests for third-party-infra live tests. (4) The at-Volatile internal var fakeX test-seam convention. (5) Per-pipe verdict extraction from trace.json disambiguating pre-init rebuild from natural pipe output.
  - 1.3.0 (2026-08-12): Five new sections + a pitfall from the uploadMapGate session. (1) Factory-builder pattern — see body. (2) TPipe Bedrock SDK auto-resolves ARNs from ~/.aws/inference.txt. (3) ConfigSource.property throws vs propertyOrEmpty returns "". (4) DEV_SAFETY_LIVE_TEST=1 opt-in env var pattern. (5) Premature-completion discipline.
---

# Autogenesis Agent-Pipe Model Audit

## 30-second mental model

The Autogenesis server runs **three live orchestrators** that wire together ~30 LLM-agent builders, each composed of one or more `BedrockMultimodalPipe` instances. Every pipe has up to four slots that may carry a model name, plus one dynamic swap path. A migration scope is the union of all slot assignments across the fleet — easy to under-count if you grep by symbol alone.

| Slot | API pattern | Meaning |
|---|---|---|
| **Main** | `setModel(BedrockConfig.X)` in a `BedrockMultimodalPipe().apply { ... }` | Primary inference call. Fires on every parent agent turn. |
| **Reasoning** | `setReasoningPipe(<builder>).apply { setModel(...) }` or chained `.apply { setReasoningPipe(...) }` | CoT step BEFORE the main call. Separate inference. |
| **Branch / Fallback** | `setBranchPipe(<builder>)` — builder's own `setModel` line is the slot | Fires ONLY when the main pipe's validator returns false. |
| **Validator** | `setValidatorPipe(buildTPipeValidatorPipe(...))` | Compliance check. Already on `qwenCoder30B` (ValidatorPipeAgent.kt:42). Usually NOT in scope. |
| **Swap** | `swapPipelineModels` (gameplayOrchestrator.kt:2748) | Dynamic in-place rewrite on retry. LIVE for deepseek/novaPro → X. |

**Dead-config trap:** `BedrockConfiguration(region=..., model=BedrockConfig.X)` constructed but never passed to a pipe. Looks live in a grep but is vestigial (canonical example: `nemesisCreationBuilder.kt:125` `qwenBedrockSettings`).

## Where the central constants live

- `server/src/main/kotlin/globals/BedrockConfig.kt` — `val qwen235B` at :421, `val qwenCoder30B` at :436, `val PalmyraX5` at :450, `val novaModelName` at :396, plus wired-up `claudeModelName`, `llamaMaverick`, `llama70B`, `llama405B`, `novaProModelName`, `jambaModelName`, `deepseekV31`, `deepseekModelName`, `PalmyraX5` (props-driven). Constants declared but not wired anywhere: `qwen32B`, `qwenCoder480B`, `qwenNext80B`, `qwenVL`.
- `server-extend/src/main/kotlin/globals/ExtendModelDefaults.kt` — mirror constants. Only `novaModelName` is wired in server-extend; `qwen235B` at :38 is declared but unused.
- `sharedModel/src/jvmMain/kotlin/org/ttt/autogenesis/config/ConfigSource.jvm.kt` — runtime config loader for properties-driven values.

Orchestrator code never inlines model IDs — it ALWAYS references the `BedrockConfig` symbol. Migration = change either (a) every reference, or (b) the symbol's string value in `BedrockConfig.kt`.

## Audit methodology (7 steps)

1. **Grep the symbol across all production sources.**
   ```bash
   grep -rn --include="*.kt" -n "BedrockConfig\.qwen235B" server/src/main server-extend/src/main
   ```
   The `-n` is critical — file:line evidence is the deliverable. Result count = scope size.

2. **For each occurrence, read the file. Classify the slot.** Use the API patterns table above. Reasons over grep alone — a `setModel` line inside a `setReasoningPipe(...)` block is NOT a Main slot.

3. **For each Main occurrence, find the orchestrator that calls its builder.** Three live orchestrators:
   - `agent.runners.executePlayerTurn` — gameplayOrchestrator.kt:353 — 12-phase player turn
   - `agent.runners.executeNpcTurn` — npcOrchestrator.kt:356 — NPC turn
   - `agent.runners.runSummitOrchestration` — SummitOrchestrator.kt:47 — multi-player summit
   Server-extend has one LLM builder wired (`commanderCreationBuilder.kt`, uses `novaModelName`) — usually out of scope.

4. **Map builder → orchestrator call site.** Builders follow `build[A-Z][a-zA-Z]*` naming. Each builder is invoked from one (or sometimes several) orchestrators. Use `grep -n "build[A-Z][a-zA-Z]*" server/src/main/kotlin/agent/runners/*.kt` to find call sites.

5. **Flag the dynamic swap path.** `swapPipelineModels` (gameplayOrchestrator.kt:2748, called from gameplayOrchestrator.kt:1045, :1149 and npcOrchestrator.kt:484) rewrites the pipe's model in-place on retry. If the target model appears in the swap's `if`/`else if` chain, it's a LIVE retry path even if no other code references it directly.

6. **Mark dead/non-live occurrences.**
   - Pricing/cost files (`game_cost_estimator.py`, `plan_tiers.py`) — DO NOT change without explicit scope, but DO update when billing model changes
   - Markdown docs (`AGENTS.md`, `CLAUDE.md`, `PLANS/*.md`, `docs/*.md`, `unlock_before_refactor_changes.md`) — informational only
   - Test files (`server/src/test/kotlin/...`) — pin current behavior; review before changing
   - `BedrockConfiguration` objects never passed to a pipe — vestigial dead config
   - Mirror constants in `ExtendModelDefaults.kt` with no usage — safe to leave
   - Symlinks and build artifacts — exclude

7. **Produce the deliverable.** Two tables:
   - **Scope table** — file:line, slot (Main/Reasoning/Branch/Validator/Swap/Dead), builder name, orchestrator wiring, replacement slot
   - **Exclusion list** — explicitly call out non-source occurrences so the user knows what was considered and excluded

## Pitfalls

**Pitfall 1 — Misleading log messages.** The log string at `gameplayOrchestrator.kt:2760` says "QwenCoder480B" but the actual code uses `qwen235B`. Always read the code, never trust log strings. (Discovered 2026-07-25.)

**Pitfall 2 — Reasoning pipe models hide inside `.apply { ... }` blocks.** `setReasoningPipe(BedrockConfig.authorBuilder(...).apply { setModel(BedrockConfig.X) })` is hard to spot in a textual grep because the surrounding call is the builder. Always check what each `.apply { setModel(...) }` block targets — it may be inside a reasoning pipe, not the main pipe. Concrete examples from the 2026-07-25 audit: `chatAgent.kt:48`, `playerAgent.kt:280`, `UserActionClassificationAgent.kt:59`.

**Pitfall 3 — Shared factory = amplified blast radius.** `buildBranchFailureAgent(instructions: String)` (BranchFailureAgent.kt:20) is a SHARED factory used by ~12 agents via `setBranchPipe(buildBranchFailureAgent(...))`. One `setModel` line in the factory affects every parent. When migrating, count the PARENTS, not the factory.

**Pitfall 4 — Dead configs that look live.** `BedrockConfiguration(...)` objects with the target model name look live in a grep but are vestigial if no pipe consumes them. Always check if the variable is passed to `reasonWithBedrock()` or similar. Canonical example: `nemesisCreationBuilder.kt:125` `qwenBedrockSettings` — defined, type-checked, never read.

**Pitfall 5 — Server-extend mirror constants are decoupled.** `ExtendModelDefaults.kt:38` declares `val qwen235B = ...` but server-extend's only LLM builder (`commanderCreationBuilder.kt`) uses `novaModelName`. Mirror constants can drift; check USAGE, not just declaration.

**Pitfall 6 — Constant symbol vs constant value.** Migrating a model can be done two ways:
- **(a)** Change the string value of the symbol in `BedrockConfig.kt:421` — smaller diff, hides the change from grep, but every existing reference still uses the OLD model name in source
- **(b)** Add a new symbol (e.g. `val primaryGenerativeModel = "qwen.qwen3-coder-30b-a3b-v1:0"`) and update every reference — larger diff, easier to audit
For production migrations, **(b) is preferred** because it makes the diff self-documenting. For ad-hoc aliasing, (a) is fine.

**Pitfall 7 — Swap path logs the WRONG name.** `swapPipelineModels` at gameplayOrchestrator.kt:2760 logs "QwenCoder480B" while swapping to `qwen235B`. If you grep logs to find the swap path, you'll miss it. Search the code, not the log strings.

## Orchestrator entry points (verified 2026-07-25)

| Orchestrator | File:line | What it wires |
|---|---|---|
| `executePlayerTurn` | gameplayOrchestrator.kt:353 | All player-turn builders; calls `runSummitOrchestration` at L650 when a Summit play is detected |
| `executeNpcTurn` | npcOrchestrator.kt:356 | NPC builder invocations: ElderGod, Nemesis, Hostile, Actor |
| `runSummitOrchestration` | SummitOrchestrator.kt:47 | Only `buildResponseRefinementAgent` + `buildJudge` |

The 12-phase player-turn pattern is documented in `gameplayOrchestrator.kt:338-348` (header doc-comment).

## Concrete audit results

The 2026-07-25 qwen235B audit found 35 live occurrences across 22 files:
- 28 Main pipes
- 3 Reasoning pipes
- 1 Branch shared factory (`BranchFailureAgent.kt:27`) — amplified to ~12 callers
- 1 Branch per-resource fallback (`resourceUsageDetectorAgent.kt:129`)
- 1 Swap path (`gameplayOrchestrator.kt:2759`)
- 1 Dead config (`nemesisCreationBuilder.kt:125`)
- 0 live usages in server-extend

Full file:line map in `references/qwen235B-call-graph-2026-07-25.md`.

## Bedrock service-tier (Flex) audit — second dimension

After (or instead of) a model migration, the same fleet can be audited for **Flex-tier routing** eligibility. `setServiceTier(BedrockPriorityTier.Flex)` routes the request to Bedrock's cheaper / higher-latency priority tier. Not every pipe is safe to move to Flex — only ones whose output is **strict-simple** (a small classifier DTO, a boolean, an enum, a shallow list of identifiers).

This dimension emerged from the 2026-07-25 post-migration audit of the qwenCoder30B fleet (after qwen235B was replaced) and is documented in `references/qwenCoder30B-flex-call-graph-2026-07-25.md`.

### Why some pipes CAN'T go Flex

Flex-tier trades latency for cost. If a pipe produces narrative prose, multi-section world-state diffs, or nested domain objects, the user-visible quality would drop and a budget model on Flex tier risks truncation / schema drift. Specifically excluded:

- **Narrative prose pipes** — `StoryOutput`, `ThirdPersonChanges.newOutput`, action-rectifier pipes that emit rewritten text, `FinalReversalOutcome.storyAfterReversal`, `CharacterDescription` lore fields, `NpcHistoryUpdate.newHistory`. The whole POINT of these pipes is quality prose; Flex is wrong.
- **Nested world-domain pipes** — `Results` (judge.kt:67, npcJudge.kt:225) which holds `TerritoryExchange`/`AssetExchange`/`TerritoryStatChange`/`ClassifiedResources`; `MultiActorStatChanges` (judge.kt:93, npcJudge.kt:603) which holds `Map<String, StatBuff>`; `NpcResourceMapWrapper` (newcharacterscan.kt:96) which holds `Map<String, List<Resource>>`; `CharacterDescriptionArray` (newcharacterscan.kt:68) which holds 7 narrative fields per entry.
- **Reasoning pipes** — by task rule, do not mark reasoning pipes Flex regardless of output shape.
- **Dead-code pipes** — if a `build*` factory is defined but never called from any orchestrator (e.g. `buildAffectedPlayerAgent` in `affectedPlayerAgent.kt:38` — verified by `grep -rn "buildAffectedPlayerAgent" server/src/main/kotlin/agent/runners/` returning empty), do not mark it Flex. The function is unhooked.

### The "strict-simple" filter

A pipe's `setJsonOutput(T)` DTO is **strict-simple** if and only if T is composed entirely of:

| Allowed | Examples |
|---|---|
| Booleans | `isLegal`, `isVictory`, `isTrue`, `isDefeated`, `captureAttempted` |
| Enums | `ActionTargetType`, `ActionIntent`, `NpcType`, `PlayType`, `ActionType` |
| Numbers (small range) | `confidence: Double ∈ [0,1]`, `luckPoints: Int` |
| Short identifier strings | `name`, `type`, `createdBy`, `npcName`, `reason` (a sentence or two, not a paragraph) |
| Shallow lists of the above | `List<String>`, `List<SimpleDto>`, `Map<String, List<Resource>>` only if Resource itself is strict-simple |

**Disallowed triggers** (any one disqualifies a DTO):

- Any field named or documented as a `summary`, `description`, `story`, `newOutput`, `newHistory`, `changesToMake`, `reversalFailureReason`, `resultSummary`, `territoryGained`, `territoryLost`, `assetsGained`, `territoryExchanges`, `assetExchanges` — these are prose OR multi-section world diffs.
- A `MutableMap<String, T>` where T is a domain object (Player, Npc, Resource, StatBuff, etc.) — maps of complex types indicate aggregation over world state, not classification.
- A nested DTO that itself contains disallowed fields (e.g. `TerritoryExchange` is fine, but `Results` containing `MutableList<TerritoryExchange>` + `MutableList<TerritoryStatChange>` + `MutableList<AssetExchange>` is not).
- A `String` field that is documented as "rewritten narrative" or "story output" in the field's comment.

### Three insertion patterns for `setServiceTier(Flex)`

The codebase has three distinct ways pipes express Flex routing. A Flex audit must detect all three and produce a uniform output.

| Pattern | Code shape | Audit action |
|---|---|---|
| **(a) Active Flex** | `setServiceTier(BedrockPriorityTier.Flex)` line present | Already correct — list as "already Flex" in deliverable |
| **(b) Commented Flex** | `// setServiceTier(BedrockPriorityTier.Flex)` line above `setModel(...)` | Uncomment the line — produces a 1-character diff |
| **(c) Absent** | No `setServiceTier` line in the apply block | Insert a new `setServiceTier(BedrockPriorityTier.Flex)` line above `setModel(...)` |

In the 2026-07-25 audit of qwenCoder30B: 5 active-Flex, 9 commented-Flex, 8 absent. Knowing which is which lets the deliverable say "uncomment line N" vs "add line at N" — both are file:line precise, but the diff shape is different.

### Pitfalls

**Pitfall 1 — Misleading log messages.** The log string at `gameplayOrchestrator.kt:2760` says "QwenCoder480B" but the actual code uses `qwen235B`. Always read the code, never trust log strings. (Discovered 2026-07-25.)

**Pitfall 2 — Reasoning pipe models hide inside `.apply { ... }` blocks.** `setReasoningPipe(BedrockConfig.authorBuilder(...).apply { setModel(BedrockConfig.X) })` is hard to spot in a textual grep because the surrounding call is the builder. Always check what each `.apply { setModel(...) }` block targets — it may be inside a reasoning pipe, not the main pipe. Concrete examples from the 2026-07-25 audit: `chatAgent.kt:48`, `playerAgent.kt:280`, `UserActionClassificationAgent.kt:59`.

**Pitfall 3 — Shared factory = amplified blast radius.** `buildBranchFailureAgent(instructions: String)` (BranchFailureAgent.kt:20) is a SHARED factory used by ~12 agents via `setBranchPipe(buildBranchFailureAgent(...))`. One `setModel` line in the factory affects every parent. When migrating, count the PARENTS, not the factory.

**Pitfall 4 — Dead configs that look live.** `BedrockConfiguration(...)` objects with the target model name look live in a grep but are vestigial if no pipe consumes them. Always check if the variable is passed to `reasonWithBedrock()` or similar. Canonical example: `nemesisCreationBuilder.kt:125` `qwenBedrockSettings` — defined, type-checked, never read.

**Pitfall 5 — Server-extend mirror constants are decoupled.** `ExtendModelDefaults.kt:38` declares `val qwen235B = ...` but server-extend's only LLM builder (`commanderCreationBuilder.kt`) uses `novaModelName`. Mirror constants can drift; check USAGE, not just declaration.

**Pitfall 6 — Constant symbol vs constant value.** Migrating a model can be done two ways:
- **(a)** Change the string value of the symbol in `BedrockConfig.kt:421` — smaller diff, hides the change from grep, but every existing reference still uses the OLD model name in source
- **(b)** Add a new symbol (e.g. `val primaryGenerativeModel = "qwen.qwen3-coder-30b-a3b-v1:0"`) and update every reference — larger diff, easier to audit
For production migrations, **(b) is preferred** because it makes the diff self-documenting. For ad-hoc aliasing, (a) is fine.

**Pitfall 7 — Swap path logs the WRONG name.** `swapPipelineModels` at gameplayOrchestrator.kt:2760 logs "QwenCoder480B" while swapping to `qwen235B`. If you grep logs to find the swap path, you'll miss it. Search the code, not the log strings.

**Pitfall 8 — "Strict-simple" filter requires reading the DTO, not just the pipe name.** Two pipes named the same way (both `setJsonOutput(Legal?)`) ARE strict-simple; two pipes named differently (one `setJsonOutput(Results)`, one `setJsonOutput(MultiActorStatChanges)`) BOTH contain nested world domain objects and are excluded. The filter is on the OUTPUT SCHEMA shape, not on the pipe's role in the orchestration. A quick mental test: does the DTO contain ANY field named like a domain entity, or a `Map<String, *>` over a domain type, or a `List<DtoThatHoldsDomainObjects>`? If yes, excluded. (Discovered 2026-07-25 during qwenCoder30B Flex audit — `judge.kt:326 gainsAndLossesPipe` and `judge.kt:1317 statChangePipe` both LOOKED like they might be classifiable, but their output schemas `Results` and `MultiActorStatChanges` each pull nested world domain objects.)

**Pitfall 9 — Validator sub-pipes on a non-target main pipe.** `reverseAgent.kt:108` is a `validatorPipe` defined inside `buildReverseAgent()`. The MAIN `reversalPipe` at L77 uses `qwen235B` (NOT in qwenCoder30B scope). But the validatorPipe inside it uses `qwenCoder30B` and IS qwenCoder30B-scope. Don't confuse the parent pipe's model with the validator sub-pipe's model — the audit follows the model constant, not the parent.

**Pitfall 10 — Already-Flex pipes that aren't strict-simple.** The task rule "Existing Flex calls count as already correct" means you don't UN-set Flex on a pipe whose output isn't strict-simple. You just note in the deliverable that the pipe is "already Flex (non-strict-simple, leaving as-is)." Three qwenCoder30B pipes were in this state in the 2026-07-25 audit: `descriptionBuilderPipe` (newcharacterscan.kt:549, narrative lore), `newNpcResourcePipe` (L639, nested Resource map), `existingNpcResourceUpdatePipe` (L927, same). They are documented but not changed.

**Pitfall 11 — Dead builders that compile.** `buildAffectedPlayerAgent` (affectedPlayerAgent.kt:38) compiles, has a `setModel(qwenCoder30B)` line, and looks like a real builder. But `grep -rn "buildAffectedPlayerAgent" server/src/main/kotlin/agent/runners/` returns nothing — no orchestrator calls it. Marking it Flex would compile but is wasted work. Always verify the builder has a live call site before recommending changes.

**Pitfall 12 — `@Ignore` annotation defeats env-var opt-in.** A live test that has BOTH `@Ignore(...)` AND `assumeTrue(env_var)` will always report `SKIPPED` regardless of the env var — `@Ignore` short-circuits JUnit before the body runs, so `assumeTrue` never executes. Verified 2026-08-10 on `MapUploadSafetyAgentLiveTest`: gradle printed `SKIPPED` even with `BEDROCK_MANTLE_LIVE_TEST=true` exported in the same shell. The canonical fix is env-var-only — drop the `@Ignore` annotation entirely and let `assumeTrue` be the sole gate. Companion rule: never edit `@Ignore` in source to temporarily re-enable a live test (the source-edit-every-inspection-run pattern compounds across iterations and pollutes diffs). Inspection runs become a one-liner: `BEDROCK_MANTLE_LIVE_TEST=true ./gradlew :module:test --tests 'ClassName' --rerun-tasks`.

### Three-orchestrator rule carries over

The Flex audit uses the same orchestrator-wiring table as the model-migration audit. Builders that are live for the 12-phase player turn or NPC turn are candidates; builders invoked only by the Summit orchestrator are also candidates. Builders with NO orchestrator wiring (Pitfall 11) are excluded.

## Live verification & trace dissection

After applying model migrations or Flex-tier changes to a live pipe, verify with the live test that already exists for that pipe — don't write a new one. The trace JSON the live test writes to `~/.tpipe/debug/trace/<sub>/trace.json` is the receipt. Traces can be enormous (the 2026-08-10 Gondwana safety run produced 42 MB), so a scripted dissection is faster than `cat | grep`.

### Three-step recipe for live verification

1. **Confirm env-var-only gating.** Open the live test file. If it has `@Ignore(...)`, drop it (Pitfall 12). The only gate should be `assumeTrue(... System.getenv(...) == "true")`.
2. **Run with the gate set in the SAME shell.** Subshells do not inherit exports:
   ```bash
   export BEDROCK_MANTLE_LIVE_TEST=true
   ./gradlew :server-extend:test --tests 'network.MapUploadSafetyAgentLiveTest' --rerun-tasks -i --no-daemon
   ```
   Look for `STANDARD_OUT` lines including `Pipe names found:` and `Safety verdict:`. A `SKIPPED` line means the env var was not seen.
3. **Dissect the trace JSON to extract per-pipe verdicts.** The answer for each pipe is `content.text` of the LAST `API_CALL_SUCCESS` event for that `pipeName`. See `scripts/extract-pipe-verdicts.py` — a static helper that walks the trace, groups events by `pipeName`, finds the final `API_CALL_SUCCESS` per pipe, and prints the LLM JSON output plus `metadata.model` / `metadata.totalInputTokens` / `metadata.totalOutputTokens` for the receipt.

### Map-resource swap pattern (live-test fixture rotation)

Live tests load map packs from `server/src/main/resources/maps/<name>.map` via the classpath. Two changes rotate the fixture: (a) update the `mapResourcePath` constant in the live test (typically a private val at the top of the class); (b) update the matching line in the KDoc comment block that names the fixture. Verified 2026-08-10: `maps/Arctica.map` → `maps/Laurasiagondwana.map` (~2.3 MB unpacked image, 90 pins). Always verify the fixture exists at BOTH `src/main/resources/maps/` AND `build/resources/main/maps/` (the latter is the compiled classpath copy) — otherwise the test fails with `getResourceAsStream returned null`.

## Quick checklist for any model migration

- [ ] Confirm target model ID is the one you want (check AWS Bedrock console / pricing page, not docs)
- [ ] Grep the symbol across `server/src/main`, `server-extend/src/main`, `kvisionApp/src/jsMain` (no JS should reference BedrockConfig directly, but verify)
- [ ] For each hit, classify slot (Main / Reasoning / Branch / Validator / Swap / Dead)
- [ ] For each Main slot, identify orchestrator call site
- [ ] Find and verify the swap path
- [ ] Update pricing files (`game_cost_estimator.py`, `plan_tiers.py`) if billing model changes
- [ ] Update `BedrockConfig.kt` constant value OR introduce a new symbol and migrate references
- [ ] Build & run integration tests for the affected agents

## Quick checklist for a Flex-tier eligibility audit (post-migration)

- [ ] Pick the target model constant (typically the newly-migrated primary, e.g. `qwenCoder30B`)
- [ ] Grep `setModel(BedrockConfig.<TARGET>)` and `model = <TARGET>` across `server/src/main`
- [ ] For each Main hit, classify: live (orchestrator call site exists) or dead
- [ ] For each live Main hit, read the DTO passed to `setJsonOutput(...)` and apply the strict-simple filter
- [ ] For each hit that has a `setServiceTier(BedrockPriorityTier.Flex)` line: classify as (a) active, (b) commented, (c) absent
- [ ] Deliverable columns: file:line, pipe name, output DTO, strict-simple YES/NO, Flex state (active/comment-ready/absent), recommended action (uncomment N / insert at N / leave)
- [ ] Separate "already-Flex" non-strict-simple pipes into a "leaving as-is" footnote (Pitfall 10)
- [ ] Verify the orchestrator call site exists for every recommended insertion (Pitfall 11)

## DITL pre-init hooks - the content-rebuild pattern for split-payload pipes (added 2026-08-10)

A pipe that receives a multimodal payload containing multiple artifacts (image bytes AND structured JSON, audio bytes AND transcript text, etc.) and routes each artifact to a DIFFERENT downstream pipe needs to filter its own view before firing the LLM. The third DITL hook variant - `setPreInitFunction { (content: MultimodalContent) -> Unit }` (declared at Pipe.kt:1632 / 4726) - rebuilds the inbound content fragment in place so the pipe's LLM only sees its domain.

### The two-step pattern

**Step 1 - bind the artifact to the pipe's metadata** at construction time so the pre-init hook can read it back:

```kotlin
val imageChecker = BedrockMultimodalPipe().apply {
    setPipeName("image pipe")
    setRegion("us-east-2")
    useConverseApi()
    setServiceTier(BedrockPriorityTier.Flex)
    setModel(BedrockConfig.novaModelName)
    // ... budget, reasoning, etc. ...

    // Bind the artifact the pipe should see onto pipeMetadata.
    pipeMetadata["imageBytes"] = imageBytes  // ByteArray from the builder's local

    setPreInitFunction {
        Logger.debug(LogCategory.SYSTEM, "MapSafety: imageCheckerPipe.setPreInitFunction entry")
        val img = pipeMetadata["imageBytes"] as? ByteArray
        if (img != null) {
            it.text = ""                                          // wipe inbound text
            it.binaryContent = mutableListOf()                    // wipe inbound binaries
            it.addBinary(img, mimeType = "image/png", filename = "map-image.png")  // reattach only what THIS pipe needs
        } else {
            it.terminatePipeline = true                           // fail-closed if metadata is missing
        }
        Logger.debug(LogCategory.SYSTEM, "MapSafety: imageCheckerPipe.setPreInitFunction success")
    }
    // ... system prompt, footer, validator, onFailure, etc. ...
}
```

**Step 2 - the mirror pattern in the sibling pipe** that consumes the OTHER artifact. The two pipes see disjoint content fragments:

```kotlin
val contentChecker = BedrockMultimodalPipe().apply {
    setPipeName("text pipe")
    // ... same config pattern ...
    pipeMetadata["mapDataJson"] = serialize(mapData)  // String from the builder's local

    setPreInitFunction {
        val mapJson = pipeMetadata["mapDataJson"] as? String
        if (mapJson != null) {
            it.binaryContent = mutableListOf()       // discard any image bytes that leaked in
            it.text = mapJson                        // reattach only the JSON
        } else {
            it.terminatePipeline = true
        }
    }
    // ...
}
```

After the pre-init hooks fire, the image pipe sees ONLY the PNG bytes and the text pipe sees ONLY the serialized JSON. Verified 2026-08-10 on `MapUploadSafetyAgentLiveTest` - the two pipes produced distinct LLM verdicts (image pipe talked about the picture, text pipe talked about the JSON).

### Why null-metadata needs the terminatePipeline guard

If the artifact was never bound (callers can construct the builder with a tampered payload, or a future refactor drops the `pipeMetadata[...] = ...` line), the pre-init hook runs but `pipeMetadata["imageBytes"] as? ByteArray` returns null. Without the guard, the LLM fires on a content fragment that has its text and binaries wiped to empty - it produces a degenerate verdict (or worse, an exception). The fail-closed `it.terminatePipeline = true` makes the pipe abort cleanly so the caller sees the gate's `safety rejected` path instead of a misleading "passed but with junk verdict" outcome.

### Three failure modes to recognize when wiring this pattern

**(a) Forgetting the import** - `pipeMetadata` is a `protected var` on `Pipe` (Pipe.kt:1933) so it's in scope inside the apply block, but `setPreInitFunction` is a builder method on the same class, no extra import needed. CONFIRMED working without new imports.

**(b) Logger not imported** - if the pre-init hook calls `Logger.debug(...)` but `org.ttt.autogenesis.logging.Logger` and `LogCategory` are not imported, compile fails with `Unresolved reference 'Logger'` and the WHOLE test class fails to compile (not just the test file). Import BOTH at the top of the file alongside the existing imports.

**(c) `multimodalContent.binaryContent` is a MutableList assignment, not a `.clear()` call** - `MultimodalContent.binaryContent` is a `var MutableList<BinaryContent>` (BinaryContent.kt:120). The rebuilder pattern is `it.binaryContent = mutableListOf()` (replace the reference), NOT `it.binaryContent.clear()` (clear in place). Either works for the wipe but only the assignment approach is consistent with the `MultimodalContent` data-class copy semantics.

### Why this pattern is reusable

Any pipe that receives a multi-artifact payload and needs to see only its slice can use this exact shape. The artifact lives on `pipeMetadata`, the pre-init hook reads it back, wipes the inbound content, and reattaches only the slice. The pattern generalizes to:

- Audio pipes (text pipe sees transcript, audio pipe sees binary audio)
- Multi-image pipes (each pipe sees its assigned image)
- Mixed-modal pipes (image+text classifiers that need to see one or the other but not both at once)

The two mirror pipes in `mapSafetyBuilder.kt` are the canonical reference implementation. Verified 2026-08-10 with two distinct LLM verdicts on a real Bedrock + Gondwana run.

## The TPipe-blessed-serializer preference - `com.TTT.Util.serialize` over `Json.encodeToString` (added 2026-08-10)

When a pipe builder needs to convert a typed object to a JSON string for binding onto `pipeMetadata`, prompt injection, or trace storage, the canonical Autogenesis call is `com.TTT.Util.serialize(obj)` - NOT `kotlinx.serialization.json.Json.encodeToString(obj)` and NOT `Json.encodeToJsonElement(obj).toString()`. Operator-explicit correction mid-session 2026-08-10.

### Why TPipe's serializer wins

`com.TTT.Util.serialize` adds AI-malformed-JSON resilience on top of the straight kotlinx round-trip. For a typical pipe-builder flow (typed DTO -> serialize -> store on metadata or inject into prompt), the resilience is cheap insurance. The cost is identical to the kotlinx path for canonical inputs (the input here is always canonical because it was just deserialized upstream by `MapPackManager.unpack`).

### Where this preference applies

ANY agent-builder site that does `typedObject -> String -> pipeMetadata` or `typedObject -> String -> trace store`. The 2026-07-25 audit identified this pattern across ~6 sibling files (`elderGodAgent.kt`, `nemesisAgent.kt`, `npcHostileAgent.kt`, `identifyPlayAgent.kt`, `BranchFailureAgent.kt`, plus several in `passFailAgent/`). All of them use `serialize(obj)`; `mapSafetyBuilder.kt` was the lone outlier using `Json.encodeToString(mapData)` until the operator correction.

### Where the raw kotlinx path is still correct

- Inside TPipe itself when generating wire-format JSON for a Bedrock/GenericOpenAI SDK request body (the SDK is the consumer, not an LLM)
- When the caller explicitly wants to BYPASS malformed-JSON repair for diagnostic purposes
- When the round-trip is canonical and the resilience overhead is measurable (rare)

### Import shape

```kotlin
import com.TTT.Util.serialize
```

Single import, no additional dependency. The function is in the `com.TTT.Util` package alongside `extractJson` (already imported by most agent files).

## Diagnostic-fail-loudly tests for third-party-infra live tests (added 2026-08-10)

A live test that exercises an external dependency (Bedrock, AGS, IAM, MatchPool, etc.) needs to distinguish THREE failure modes:

1. **Code defect** - the production code is wrong, fix it
2. **Test bug** - the test asserts incorrectly, fix the test
3. **Third-party-infra outage** - AGS/Bedrock/IAM is down, NOT a code defect - retry later or escalate to the vendor

A test that asserts only `assertTrue(saved, "savePlayerMap must succeed")` reports failure mode 3 as a generic "save failed" assertion. The next agent that sees the failure has to re-read the source, find the AGS call, recognize the 500 from the error message, and figure out it's an infra outage. That's a 5-10 minute diagnosis tax EVERY time the test fails for an infra reason.

### The diagnostic-fail-loudly pattern

Add a SEPARATE test class whose ONLY purpose is to detect the third-party-infra outage case and emit a diagnostic message that names the third party explicitly. Canonical example from `MapStorageProxyLiveTest.kt:165`:

```kotlin
@Test
fun diagnosticSavePlayerMapAgainstLiveAgs(): Unit = runBlocking {
    assumeTrue("set AGS_LIVE_TEST=true", liveTestEnabled())
    assumeTrue("no credentials file", credentialsAvailable())
    val ns = namespaceFromEnv()
    assumeTrue("AB_NAMESPACE must be exported", !ns.isNullOrBlank())
    val namespace = ns!!

    val userId = System.getenv("AB_LIVE_TEST_USER") ?: "25a70be88881466286bc03154f5d7492"
    val mapId = UUID.randomUUID().toString()
    val pack = "diagnostic-${System.currentTimeMillis()}".toByteArray()

    val saved = MapStorageProxy.savePlayerMap(ctx, SavePlayerMapRequest(
        userId = userId, mapId = mapId, mapName = "diagnostic",
        mapPackBytes = pack
    ))
    // When AGS returns 500 (l5d-proxy-error), this fails loudly so CI
    // surfaces the breakage - NOT silently green. The test asserts success
    // because savePlayerMap MUST succeed; AGS infrastructure health is
    // out of band for this test's contract.
    assertTrue(
        saved,
        "savePlayerMap against live AGS FAILED - AGS endpoint adminCreatePlayerBinary is returning " +
        "HTTP 500 l5d-proxy-error for namespace=$namespace userId=$userId. " +
        "This is an AGS infrastructure issue (Linkerd service mesh), NOT a code defect. " +
        "Investigate via AccelByte Admin Portal or support ticket."
    )
}
```

### What the diagnostic message MUST contain

- The third-party endpoint name (e.g. `AGS endpoint adminCreatePlayerBinary`)
- The error signature seen (e.g. `HTTP 500 l5d-proxy-error`)
- The namespace/userId from the test's actual run context
- The verdict that this is NOT a code defect
- The next action (open a vendor ticket, retry, escalate)

Without these, the test failure is a wall the next agent has to climb. With them, the next agent reads the failure message and immediately knows what to do.

### When this pattern is NOT appropriate

- Pure unit tests that mock the third-party dep - the mock already produces predictable failures
- Tests that ALREADY emit detailed error messages via `Logger.error(...)` with the third-party name in the message - check the logs before adding a duplicate test
- Tests where the third-party name is already in the assertion failure string (most modern assertion libraries do this; check `kotlin.test.assertEquals` output)

### Reference case

2026-08-10 smoke check on `MapStorageProxyLiveTest.diagnosticSavePlayerMapAgainstLiveAgs`: surfaced the AGS Linkerd outage (HTTP 500 l5d-proxy-error) on the FIRST attempt, with a message naming AGS as the failing party and instructing the operator to file a vendor ticket. Without this pattern, the failure would have been a generic "assertTrue(saved) was false" that the next agent would have to re-diagnose from scratch.

## The `@Volatile internal var fake<X>` test-seam convention for Autogenesis gateway classes (added 2026-08-10)

A class that wraps an external dependency (Bedrock, AGS, S3, etc.) and exposes a single orchestrating method needs a test-seam pattern that lets unit tests bypass the dependency without mocking the world. The canonical Autogenesis convention is `@Volatile internal var fake<X>: ((...) -> Result)? = null` declared on the singleton/object, plus a `resetForTest()` companion that nulls all the fakes. Canonical example: `MapUploadGate` (server-extend) plus `MapUploadGateStorage` (server-extend).

### The shape (4 pieces)

```kotlin
object MapUploadGate {
    /** Test seam - when non-null, overrides the real unpack call. */
    @Volatile
    internal var fakeUnpacker: ((ByteArray) -> MapSafetyPayload)? = null

    /** Test seam - when non-null, overrides the safety pipeline call. */
    @Volatile
    internal var fakeSafetyRunner: ((playerId: String, payload: MapSafetyPayload) -> MultimodalContent)? = null

    /** Test seam - when non-null, overrides the downsample helper. */
    @Volatile
    internal var fakeDownsampler: ((ByteArray) -> ByteArray)? = null

    internal fun resetForTest() {
        fakeUnpacker = null
        fakeSafetyRunner = null
        fakeDownsampler = null
    }

    @RpcMethod("server.extend.uploadMapGate", RpcDirection.SERVER)
    suspend fun uploadMapGate(context: RpcCallContext, request: MapUploadRequest): MapUploadGateResponse {
        // 1. Unpack (real or fake)
        val payload = try {
            val unpacker = fakeUnpacker
            if (unpacker != null) unpacker(request.mapPackBytes)
            else { val unpacked = MapPackManager.unpack(request.mapPackBytes); MapSafetyPayload(...) }
        } catch (e: Exception) { ... }

        // 2. Pre-flight downsample (real or fake)
        val imageBytes = if (payload.imageBytes.size > MAX_SAFE_BINARY_BYTES) {
            val downsampled = downsampleImageBytes(payload.imageBytes)  // delegates to fakeDownsampler internally
            // ...
        } else payload.imageBytes

        // 3. Safety pipeline (real or fake)
        val safetyPass = try {
            val runner = fakeSafetyRunner
            val result = if (runner != null) runner(playerId, payload)
            else {
                val pipeline = buildMapSafetyAgent(playerId, payload)
                pipeline.enableTracing(...)
                val multimodal = MultimodalContent(text = "Map upload safety check")
                multimodal.addBinary(imageBytes, mimeType = "image/png", filename = "map.png")
                val pipelineResult = pipeline.execute(multimodal)
                captureAndSaveTrace(pipeline, playerId)
                pipelineResult
            }
            !result.shouldTerminate()
        } catch (e: Exception) { ... }
        // ... save + notify + return ...
    }

    private fun downsampleImageBytes(bytes: ByteArray): ByteArray {
        val fakeDownsampler = fakeDownsampler
        if (fakeDownsampler != null) return fakeDownsampler(bytes)
        try { /* real ImageIO downsample */ } catch (e: Exception) { return bytes }
    }
}
```

And the storage-layer twin:

```kotlin
object MapUploadGateStorage {
    @Volatile
    internal var fakeSaver: ((context: RpcCallContext, request: SavePlayerMapRequest) -> Boolean)? = null

    internal fun resetForTest() {
        fakeSaver = null
    }

    suspend fun savePack(
        context: RpcCallContext, userId: String, mapId: String, mapName: String, mapPackBytes: ByteArray
    ): Result<Unit> {
        val saver = fakeSaver
        val request = SavePlayerMapRequest(userId, mapId, mapName, mapPackBytes, contentType = "application/zip")
        return runCatching {
            val ok = if (saver != null) saver(context, request)
            else MapStorageProxy.savePlayerMap(context, request)
            if (!ok) throw RuntimeException("MapStorageProxy.savePlayerMap returned false for $userId/$mapId")
        }
    }
}
```

### Why this shape and not a mocking framework

- No mocking-framework dependency (Mockito-Kotlin, MockK) - keeps the test classpath thin
- The seams are object-scoped (not per-test), so a `@Before`/`@After` can null them in one call via `MapUploadGate.resetForTest()` plus `MapUploadGateStorage.resetForTest()`
- The fakes are typed lambdas with the SAME signature as the real seam (e.g. `(ByteArray) -> MapSafetyPayload`), so the production code path doesn't change shape when a fake is installed
- `@Volatile` makes the seams safe across concurrent test JVMs (gradle runs tests in forked JVMs but a single JVM may still have parallel test methods)

### The companion test pattern

```kotlin
@Before
fun setUp() {
    MapUploadGate.resetForTest()
    MapUploadGateStorage.resetForTest()
}

@After
fun tearDown() {
    MapUploadGate.resetForTest()
    MapUploadGateStorage.resetForTest()
}

@Test
fun safetyRejectTriggersErrorHandler() = runBlocking {
    // Install fakes BEFORE the gate call
    MapUploadGate.fakeUnpacker = { MapSafetyPayload(imageBytes = byteArrayOf(), mapData = ...) }
    MapUploadGate.fakeSafetyRunner = { _, _ -> MultimodalContent().apply { terminatePipeline = true } }
    MapUploadGateStorage.fakeSaver = { _, _ -> true }

    val ctx = RpcCallContext(connectionId = "test-player", sender = { })
    val response = MapUploadGate.uploadMapGate(ctx, MapUploadRequest(mapPackBytes = byteArrayOf(), mapName = "test"))

    assertFalse(response.accepted)
    // assertions on the captured error handler invocations
}
```

The test exercises the gate's orchestration logic without ever touching Bedrock, AGS, S3, or ImageIO. Verified working: `MapUploadGateTest.kt` and `MapUploadGateTraceTest.kt` both run entirely on fakes.

### When to introduce this pattern vs. mocking

Use the `fake<X>` seam when:
- The class is an `object` (singleton) or top-level holder that wraps external I/O
- Multiple test classes need to bypass the same dependency in different ways
- The dependency is real production code (Bedrock, AGS, S3) where mocking-the-world via MockK would be fragile

Use MockK/Mockito when:
- The class is a regular instance (not an object)
- The seam is per-test-instance and one-off
- The class has many small methods that each need separate mock behavior

For Autogenesis gateway classes (MapUploadGate, MapStorageProxy, BinaryRecordProxy, CloudSaveProxy), the `fake<X>` seam is the consistent convention - it produces uniform test code across the proxy layer.

## Per-pipe verdict extraction from trace.json - pre-init rebuild vs natural pipe output (added 2026-08-10)

The trace-dissection recipe in the "Live verification and trace dissection" section above (final `API_CALL_SUCCESS` per pipeName) needs an extension when the pipe uses `setPreInitFunction` to REBUILD its content. Verified 2026-08-10 on `MapUploadSafetyAgentLiveTest` after the pre-init DITL hooks were added.

### The disambiguation problem

After pre-init hooks, the trace event chain per pipe looks like:

```
ev#2  CONTEXT_PREPARED     (textLen = 0)
ev#3  API_CALL_START       (textLen = 0)
ev#4  API_CALL_START       (textLen = 0)
ev#5  API_CALL_START       (textLen = 0)
ev#6  API_CALL_START       (textLen = 0)
ev#7  API_CALL_START       (textLen = 0)
ev#8  API_CALL_SUCCESS     (textLen = 0)             # pre-init hook fired, inbound content wiped
ev#9  API_CALL_SUCCESS     (textLen = 80915)         # echoed inbound content (NOT the LLM verdict)
ev#10 API_CALL_SUCCESS     (textLen = 80915)         # same echoed content (cache or replay)
ev#11 POST_GENERATE        (textLen = 0)             # post-gen hook fired
ev#12 API_CALL_SUCCESS     (textLen = 80915)         # STILL the echoed content, not the verdict
ev#13 VALIDATION_START     (textLen = 80915)
ev#14 VALIDATION_SUCCESS   (textLen = 80915)
ev#15 PIPE_SUCCESS         metadata.outputText = "```json\n{isAllowed: true, ...}\n```"
```

The first `API_CALL_SUCCESS` events show the inbound content (echoed by the SDK before the LLM processes it). The LLM's actual verdict is in `metadata.outputText` on the `PIPE_SUCCESS` event - NOT in the `API_CALL_SUCCESS.content.text`.

### The correct extraction target

```python
# WRONG - picks the first API_CALL_SUCCESS which echoes inbound content
ev = next(e for e in events if e.get('pipeName') == 'image pipe' and e.get('eventType') == 'API_CALL_SUCCESS')
text = ev['content']['text']  # contains the echoed inbound map JSON, not the LLM verdict

# CORRECT - walk events in REVERSE order to find the LAST API_CALL_SUCCESS that
# immediately precedes VALIDATION_SUCCESS or PIPE_SUCCESS
for ev in reversed(events):
    if ev.get('pipeName') == 'image pipe' and ev.get('eventType') == 'API_CALL_SUCCESS':
        text = ev.get('content', {}).get('text', '')
        if text and 'isAllowed' in text:
            break  # this is the actual LLM verdict

# ALSO CORRECT - use metadata.outputText on PIPE_SUCCESS
for ev in reversed(events):
    if ev.get('pipeName') == 'image pipe' and ev.get('eventType') == 'PIPE_SUCCESS':
        ot = ev.get('metadata', {}).get('outputText', '')
        if ot:
            text = ot
            break
```

### Why the inbound content shows up in `content.text` of early events

The TPipe SDK captures the inbound content fragment at every API call boundary for trace purposes. After the pre-init hook replaces the inbound content, the SDK records the NEW content (which includes whatever the hook set, NOT just the LLM verdict). The LLM verdict appears in the SDK's response capture, which lands on `metadata.outputText` of the terminal event (`PIPE_SUCCESS` or sometimes a separate `POST_GENERATE` capture event depending on the SDK version).

### Companion recipe for the trace parser script

The existing `scripts/extract-pipe-verdicts.py` should be updated to handle the pre-init-rebuild case by:

1. Reverse-walking events to find the LAST `API_CALL_SUCCESS` per pipeName that has non-empty content with `isAllowed` substring OR has the pipe's expected output schema
2. Falling back to `metadata.outputText` on `PIPE_SUCCESS` if no API_CALL_SUCCESS matches the substring filter

This makes the trace parser robust to pipes with pre-init hooks AND pipes without (the existing behavior covers the latter case cleanly).

### Reference case

2026-08-10 Gondwana live test run: image pipe's `content.text` on the first `API_CALL_SUCCESS` events showed 80,915 chars of the inbound map JSON (echoed by SDK after pre-init hook replaced inbound content). The actual LLM verdict - "The image is a stylized world map depicting geographical boundaries and features without any explicit content..." - was in `metadata.outputText` on `PIPE_SUCCESS`. The text pipe's verdict followed the same pattern (long `content.text` echoing inbound, short verdict in `metadata.outputText`). Without the disambiguation, the agent would have reported the echoed JSON as the LLM verdict - misleading and wrong.

## The factory-builder pattern - every `build<X>Agent` MUST mirror `buildPassFailAgent` (added 2026-08-12)

A `build<X>Agent(...)` factory should never hand-roll inline pipe construction with `setOnFailure` callbacks that call RPC handlers directly. The canonical shape - documented at `passFailAgent/passFailAgent.kt` and mirrored by every other agent in the codebase (`buildCommanderCreationAgent`, `buildValidateAction`, `buildAuthorBuilder`, `buildJudge`, `buildSafeExtractor`, `buildNemesisActor`, etc.) - is the load-bearing pattern. Operator-flagged 2026-08-12 when `buildMapSafetyAgent` in `agent/builders/mapSafetyBuilder.kt` was found using a hand-rolled two-pipe construction instead.

### The canonical factory-builder shape

```kotlin
fun buildMapSafetyAgent(playerId: String, payload: MapSafetyPayload): Pipeline {
    val pipeline = Pipeline()

    val safetyPipe = BedrockMultimodalPipe().apply {
        setRegion("us-east-2")
        useConverseApi()
        setServiceTier(BedrockPriorityTier.Flex)
        setModel(BedrockConfig.<factory-built model ref>)      // NEVER raw string, ALWAYS BedrockConfig.<helper>()

        // The agent-builder machinery — NOT optional:
        requireJsonPromptInjection()
        setJsonOutput(MapSafetyCheck())                          // Schema INSTANCE, not KClass
        setTokenBudget(BedrockConfig.<budgetSettings>())
        setReasoningPipe(BedrockConfig.<factory-built reasoning>())  // factory helper, not inline
        setPageKey("previous turn, user prompt, map upload")     // for ContextBank todo-list
        forceSaveSnapshot()                                       // for /snapshot rollback
        pullPipelineContext()                                     // inherit parent's ContextBank
        // system prompt, footer, validator function (returns Boolean from extractJson)
    }

    return pipeline.apply {
        add(safetyPipe)
        // Pipeline-level setPreValidationFunction binds playerId to miniBank for the failure callback
        // Pipeline-level setOnFailure reads from minibank + emits the standard Map.Upload.Error notification
    }
}
```

### What the hand-rolled version got wrong

The 2026-08-12 `mapSafetyBuilder.kt` had:

1. **Two parallel pipes with hand-rolled `setPreInitFunction`** that wipe inbound content + reattach the artifact slice. The DITL pre-init pattern (covered earlier in this skill) is necessary for split-payload routing — but the cleaner shape is to use the factory-built reasoning pipe (which auto-handles context preparation) and a single main pipe, NOT two parallel pipes with manual wipe/reattach logic.
2. **Per-pipe `setOnFailure` callback that called `MapUploadErrorHandlers.sendMapUploadError(id, failureReason)` directly.** This couples the agent to a specific RPC handler. The factory pattern keeps failure routing at the PIPELINE level (`pipeline.setOnFailure { ... }`), which lets the orchestrator swap the pipe without rewriting the failure handler.
3. **`setModel(BedrockConfig.novaModelName)` directly.** The factory pattern usually references `BedrockConfig.<helper>()` (e.g. `BedrockConfig.bedrockLlamaStructuredCotBuilder()` for reasoning, `BedrockConfig.authorBuilder()` for narrative). Direct `setModel` skips the factory's token-budget + Flex-tier + reasoning-pipe wiring.
4. **No `setReasoningPipe(...)` line.** The factory pattern ALWAYS wires a reasoning pipe (via `BedrockConfig.<reasoningBuilder>()`). Without it, the LLM fires without structured CoT and the verdict quality drops.
5. **No `setPageKey`, `forceSaveSnapshot`, `pullPipelineContext`.** These three are the agent-builder convention for ContextBank integration; missing any one means the pipe won't participate in the page-level todo list, can't roll back on snapshot mismatch, and won't inherit parent context.

### The audit checklist for any new build<X>Agent

When reviewing a new or modified agent factory, ask:

- [ ] Returns `Pipeline()` (not raw `BedrockMultimodalPipe` — must be in a container)
- [ ] `setModel(BedrockConfig.<factory-helper>())` — never raw string
- [ ] `requireJsonPromptInjection()` or `setJsonOutput(<schema instance>)` (the latter implies the former)
- [ ] `setReasoningPipe(BedrockConfig.<reasoning-builder>())` for any non-trivial reasoning
- [ ] `setPageKey("...")` for ContextBank integration
- [ ] `forceSaveSnapshot()` if the pipe participates in a rollback flow
- [ ] `pullPipelineContext()` to inherit parent's ContextBank
- [ ] `setOnFailure` is at the PIPELINE level, NOT per-pipe
- [ ] Failure routing reads playerId from miniBank or pipeline metadata, NOT from local closure capture

A factory missing any one of these eight items is "non-canonical" - it will compile and may work, but it will not be discoverable by the agent-builder audit, will not benefit from context-injection improvements added to other factories, and will need its own bespoke failure-routing wiring.

### Why this pattern is reusable

Every agent builder in the codebase does roughly the same thing: configure a Bedrock pipe with a model, prompt, JSON output schema, validator, and failure handler. The factory-builder pattern is the uniform shape that makes all 30+ agent builders interchangeable. A new agent that hand-rolls inline construction is "off-pattern" — it will compile, work, and pass tests, but it will not be interoperable with the rest of the fleet when future refactors touch the builder pattern.

### Reference implementations to compare against

- `agent/builders/passFailAgent/passFailAgent.kt` — closest analog (single pipe, single verdict)
- `agent/builders/commanderCreationBuilder.kt` — multi-pipe with shared factory
- `agent/builders/judgeOutcome/judge.kt` — long-running validator pipeline
- `agent/builders/validateAction/validator.kt` — short-circuit validator

Every `build<X>Agent` in the codebase matches at least one of these four shapes. A factory that matches NONE is suspect.

## TPipe Bedrock SDK auto-resolves ARNs from `~/.aws/inference.txt` (added 2026-08-12)

The TPipe `bedrockEnv.loadInferenceConfig()` reads `~/.aws/inference.txt` at app startup and populates `modelToInferenceMap` with `modelId → arn` pairs. `bedrockEnv.getInferenceProfileId(modelId)` is called by `BedrockMultimodalPipe.init()` to resolve the ARN for a given model name. **No manual config in `bedrock.local.properties` is needed for the SDK to find ARNs** — the home-directory inference file is the canonical source.

### The auto-resolution chain

1. **App startup** → `BedrockConfig.<companion>.init {}` runs (JVM static init).
2. **The init block** calls `bedrockEnv.bindInferenceProfile(<modelId>, ConfigSource.property("bedrock.local.properties", "<key>"))` for every model constant. The bind just stores the value in `modelToInferenceMap` — it does NOT throw.
3. **Then** `bedrockEnv.loadInferenceConfig()` reads `~/.aws/inference.txt` (or the override file). This OVERWRITES any earlier `bindInferenceProfile` values with the home-directory values. So even if `bedrock.local.properties` has the wrong/missing key, the home-directory file wins.
4. **At pipe init**, `bedrockEnv.getInferenceProfileId(modelId)` returns the ARN from the populated map. If no binding exists, returns null — the pipe fails at the AWS SDK call site with a different error.

### Why the `bedrock.local.properties missing key 'bedrock.llamaScout17B'` log was misleading

The `BedrockConfig.kt:529` line `bedrockEnv.bindInferenceProfile(llamaScout17B, ConfigSource.property("bedrock.local.properties", "bedrock.llamaScout17B"))` THROWS because `ConfigSource.property(...)` errors on missing keys. The `init {}` block's try/catch swallows the throw and logs `Failed to initialize Bedrock inference config: bedrock.local.properties missing key 'bedrock.llamaScout17B'`.

But this is HARMLESS. The pipeline that uses `llamaScout17B` (none currently in server-extend) would fail at the AWS SDK call. The pipeline that uses `novaModelName` (= `amazon.nova-2-live-v1:0`, the actual model) is unaffected because:

- `bedrock.local.properties` HAS `bedrock.nova2LiteModelName` (line 17) with the correct ARN — bind succeeds.
- `~/.aws/inference.txt` line 2 ALSO has `amazon.nova-2-lite-v1:0` with the same ARN — `loadInferenceConfig()` overwrites with the same value.

So the `llamaScout17B` "missing key" log is a red herring. The actual model resolution path uses `nova2LiteModelName` and works end-to-end.

### Operator-corrected claim (2026-08-12)

I previously stated in `MEMORY.md` (during the 2026-08-12 uploadMapGate session): *"the only way to write a tag-only update is to bypass the SDK's wrapper layer"* — wait, that was a different thing. What I said was: *"the only way to write a tag-only update is to bypass the SDK's wrapper layer"* — that's actually correct for the AGS SDK.

What I said wrong was: *"server-extend has the safety pipeline needing `bedrock.llamaScout17B` AWS inference profile ARN in `bedrock.local.properties` or `~/.autogenesis/config/bedrock.properties`. Test `@Ignore`d in `LlamaScout17BModelBindingTest.kt:15` for the same reason."* — that claim WAS correct (the test IS @Ignore'd for that reason).

But I also said: *"Path A (operator config): Add `bedrock.llamaScout17B=<some-arn>` to `~/.autogenesis/config/bedrock.properties`..."* — this was misleading. The operator pushed back: *"you are fucking stupid the aws bedrock sdk tpipe uses resolves it automatically."* The operator was right that the SDK auto-resolves. The correct summary:

- The TPipe SDK auto-resolves ARNs from `~/.aws/inference.txt` (the canonical home-directory file).
- The `bedrock.llamaScout17B` key was only needed for the `BedrockConfig.init {}` block's bind call, which fails harmlessly and is then overwritten by `loadInferenceConfig()`.
- The real model in the safety pipeline (`novaModelName` = `amazon.nova-2-lite-v1:0`) DOES resolve correctly via the home-directory file.

### Audit checklist for "is my model finding its ARN?"

If a pipe is failing with "model not found" or "inference profile not configured" errors:

1. **Check `~/.aws/inference.txt`** — the line `modelId=arn` must exist for the model ID used in `setModel(...)`.
2. **Check `bedrock.local.properties`** — NOT necessary for the SDK to work, but the `BedrockConfig.init {}` block's try/catch will log warnings if keys are missing (harmless noise).
3. **Check `~/.aws/inference.txt` permissions** — should be `600` (root-only) for security but the SDK reads it regardless.
4. **Check `bedrockEnv.loadInferenceConfig()` is called** — happens automatically in `BedrockConfig.<companion>.init {}` on JVM startup.

The home-directory file is the source of truth. Project-level properties files are vestigial after `loadInferenceConfig()` overwrites them.

## `ConfigSource.property()` throws vs `propertyOrEmpty()` returns "" (added 2026-08-12)

A subtle but load-bearing distinction in the Autogenesis config layer:

- `ConfigSource.property(filename, key)` — STRICT. Throws `IllegalStateException("$filename missing key '$key'")` when the key is blank or missing. **The throw is caught by the calling code's try/catch.**
- `ConfigSource.propertyOrEmpty(filename, key)` — LENIENT. Returns `""` when the key is blank or missing. **No exception.**
- `readProperty(filename, key)` — INTERNAL. Returns `String?` (null when missing). Neither throws nor defaults.

### When to use each

| API | Use when | Wrong choice consequence |
|---|---|---|
| `.property()` | Key is REQUIRED for the surrounding code to function (e.g. AGS namespace) | NPE or `error("...")` — fails loud at init time |
| `.propertyOrEmpty()` | Key is OPTIONAL — code has a sensible default when blank (e.g. an inference-profile ARN that's only required if the model is used) | Wrong inference profile bound (empty string) — pipe fails later with confusing AWS SDK error |
| `.readProperty()` | Caller wants to do its own null-checking (e.g. fall back to a default or compute a value) | Same as `.propertyOrEmpty()` semantically — explicit null handling is the difference |

### Why the `BedrockConfig.init {}` block's `try/catch` matters

`bedrockEnv.bindInferenceProfile(llamaScout17B, ConfigSource.property("bedrock.local.properties", "bedrock.llamaScout17B"))` at `BedrockConfig.kt:529` USES `.property()`. When the key is missing, `.property()` throws. The surrounding `try { ... } catch (e: Exception) { Logger.error("Failed to initialize Bedrock inference config: ${e.message}") }` catches the throw and logs the harmless warning.

This pattern is fragile because:
- The catch swallows EVERY exception in the init block, not just the missing-key throw. A typo in any bind call would be silently swallowed.
- The log message says "Failed to initialize Bedrock inference config" — implying the WHOLE init failed, when in fact only ONE bind call failed.
- The silent failure of the empty-string bind means downstream calls to `getInferenceProfileId(llamaScout17B)` return null — but no one is calling that with `llamaScout17B`, so the bug is invisible.

### The fix

Replace the throwing pattern with the lenient pattern for OPTIONAL keys:

```kotlin
// BEFORE (throws when key missing, gets swallowed by catch)
bedrockEnv.bindInferenceProfile(llamaScout17B, ConfigSource.property("bedrock.local.properties", "bedrock.llamaScout17B"))

// AFTER (returns "" when missing, no throw, clean bind of empty value)
bedrockEnv.bindInferenceProfile(llamaScout17B, ConfigSource.propertyOrEmpty("bedrock.local.properties", "bedrock.llamaScout17B"))
```

The empty-string bind just registers `modelToInferenceMap[llamaScout17B] = ""`. If a pipe ever tries to call this model, it fails at the AWS SDK call site with `profile ARN cannot be empty` — a much clearer error than "the model isn't found in the inference map."

### Where this distinction matters elsewhere in the codebase

Anywhere `BedrockConfig.init {}` or similar block calls `ConfigSource.property(...)` for an OPTIONAL model key, the catch-all try/catch is masking real configuration gaps. Audit candidates:

- `server/src/main/kotlin/globals/BedrockConfig.kt:522-530` — eight `.property()` calls, all optional model keys
- `server/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:407` — `accelbyteId` is OPTIONAL (legitimately empty for anonymous/dev callers)
- `server-extend/src/main/kotlin/.../RestPlayerConnectionManager.kt` and related — properties lookups for optional features

The rule: `ConfigSource.property()` is for keys whose absence is a HARD ERROR (AGS namespace, AccelByte client credentials, bedrock region). `ConfigSource.propertyOrEmpty()` is for keys whose absence is a SOFT FALLBACK (inference profiles for unused models, optional feature flags). Use the right one to get the right behavior at init time.

## The `DEV_SAFETY_LIVE_TEST=1` opt-in env-var pattern for dev-mode safety pipelines (added 2026-08-12)

When a `build<X>Agent` factory depends on a runtime credential that may not be present in every dev environment (e.g. the Bedrock LLM credential for the map-safety pipeline, the Anthropic API key for the action-validator, the AGS namespace for any save-side path), the conventional pattern is:

1. **A `bypassSafetyInDev: Boolean` flag** on the gateway class (the object that wraps the agent factory). Default `false`.
2. **A dev-mode flag setter** in the bootstrap that flips the bypass ON when `ExtendConfig.debugMode` is true (i.e., the dev path).
3. **An opt-in env var** (`DEV_SAFETY_LIVE_TEST=1` or similar) that flips the bypass OFF when explicitly set, so an operator can verify the live pipeline on a dev machine without a permanent source edit.

The env-var pattern is critical: it lets you ship "safety bypass ON by default in dev mode" without losing the ability to "verify the real pipeline end-to-end on a dev machine" — both states are reachable, and the operator picks.

### Canonical pattern at `server-extend/.../ServerExtend.kt:141`

```kotlin
if (System.getenv("DEV_SAFETY_LIVE_TEST") == "1") {
    network.MapUploadGate.bypassSafetyInDev = false
    Logger.warn(LogCategory.SYSTEM,
        "ServerExtend: DEV_SAFETY_LIVE_TEST=1 — MapUploadGate safety pipeline is LIVE. " +
        "The Bedrock model will be invoked on every upload; uploads will run the real safety pass."
    )
} else {
    network.MapUploadGate.bypassSafetyInDev = true
    Logger.warn(LogCategory.SYSTEM,
        "ServerExtend: dev mode active — MapUploadGate safety pipeline is BYPASSED. " +
        "Set DEV_SAFETY_LIVE_TEST=1 to run the live safety pipeline against a real Bedrock model."
    )
}
```

### Why three states, not two

The naive two-state pattern is "bypass in dev, real in prod." The problem: dev environments that DO have AWS credentials (the operator's local box, CI with role assumption, a staging server with bedrock.local.properties populated) cannot run the real pipeline without a source edit. The env-var opt-in adds the third state:

- **Default (no env var, debugMode=true)**: bypass ON. The upload flow works on any machine. The safety agent is never invoked. Useful for unit tests, integration tests, dev UI iteration.
- **`DEV_SAFETY_LIVE_TEST=1` (env var set, debugMode=true)**: bypass OFF. The safety agent runs against the real Bedrock model on the dev machine. Useful for verifying a new prompt, debugging a reject path, or proving the pipeline works end-to-end on a known-good fixture.
- **`debugMode=false` (production)**: bypass OFF, regardless of env var. The safety agent always runs in production.

### Env-var conventions

- **`DEV_<AGENT_NAME>_LIVE_TEST=1`** — for live-test opt-ins (most common). Tests the agent runs end-to-end against the real third-party.
- **`ALLOW_<TICKET_NAME>` or `<NAMESPACE>_LIVE_TEST=true`** — for AGS-specific opt-ins (e.g. `AGS_LIVE_TEST=true`).
- **`BEDROCK_LIVE_TEST=true`** — for Bedrock-specific opt-ins (see `LlamaScout17BModelBindingTest` for canonical example).
- **`MANIFOLD_LIVE_TEST=true`** — for Manifold-specific opt-ins (if you have one).

The convention is: `<UPPER_SNAKE_NAME>_LIVE_TEST=true` to opt into a live test, `<UPPER_SNAKE_NAME>_BYPASS=true` to opt into a bypass, etc. The flag is read via `System.getenv(...) == "1"` or `== "true"` — the string literal convention varies but stays boolean-stringly.

### Pitfalls

**Don't use `@Ignore` for live-test opt-ins.** Use `assumeTrue(... System.getenv(...) == "true")` inside the test body. `@Ignore` short-circuits JUnit BEFORE the body runs, so the env-var check never executes — the test always reports SKIPPED regardless of the flag. Verified 2026-08-10 on `MapUploadSafetyAgentLiveTest`.

**Don't make the bypass the only path.** A `bypassSafetyInDev` flag that defaults to `true` and has NO way to opt out is just a hard-coded bypass. The env-var opt-in is the difference between "dev convenience" and "removable safety net."

**Don't bypass without a clear trace marker.** When the bypass fires, log it as `Logger.warn(...)` with the word "BYPASS" or "DEV_MODE" in the message. Operators tracing production incidents need to see the bypass marker immediately, not 100 lines deep.

### Reference cases

- `server-extend/.../ServerExtend.kt:141-176` — DEV_SAFETY_LIVE_TEST env var, opt-out of bypass
- `server/src/test/kotlin/.../LlamaScout17BModelBindingTest.kt` — BEDROCK_LIVE_TEST env var, opt-in to live test
- `server-extend/src/test/kotlin/.../MapStorageProxyLiveTest.kt` — AGS_LIVE_TEST env var, opt-in to live AGS test

All three are the same shape: env-var read at startup or test-body time, flag flipped, behavior conditional on the flag.

## Premature-completion discipline: never declare "verified" when bypass was the only path (added 2026-08-12)

When a class-level goal is "fix bug X" and the verification path involves running a probe against a permissive bypass (e.g. `bypassSafetyInDev = true` causing the safety pipeline to permissively default to pass), **the verification is INCOMPLETE**. The bypass proves the wiring (UI → RPC → save → catalogue refresh) works, but does NOT prove the real pipeline works.

This was a 2026-08-12 operator-flagged lesson. I claimed "26/28 PASS, goal complete" when the safety pipeline had only been tested through the bypass. The operator's push-back: *"did you run a live safety pass?"* — the answer was no.

### The discipline

When a fix or feature has multiple verification paths:

1. **Name the paths explicitly.** E.g.:
   - Path A: bypass ON, fixture small (proves wiring)
   - Path B: bypass OFF, fixture realistic (proves real pipeline)

2. **Mark which paths you've actually executed.** E.g.:
   - Path A: PASS (wiring works)
   - Path B: NOT EXECUTED (real pipeline unverified)

3. **Never claim "complete" or "verified end-to-end" until ALL paths have been executed.** If any path is unverified, the goal is partial — say so explicitly.

4. **Ask the operator which path to take next, with a concrete proposal.** E.g.: "Should I (a) generate a realistic 200×200 PNG fixture and re-run the probe, or (b) refactor buildMapSafetyAgent to the factory pattern first, or (c) both?"

### Why this matters

In the 2026-08-12 session, the operator's push-back came after I claimed completion. The fix cost the operator's attention to re-open a closed issue, audit my work, point out the unverified path, and direct me to verify it. The total time cost was 5-10 minutes — much more than the 30 seconds it would have taken me to NOT claim completion prematurely.

In general, the rule is: **the cost of premature completion is always higher than the cost of "I haven't finished yet."** Operators trust an agent that admits partial completion MORE than an agent that confidently claims full completion — because the partial-completion agent has fewer false-positive claims to investigate later.

### The "I haven't verified yet" template

When you can't fully verify a fix, your message should look like:

```
What works (verified):
- Path A: bypass ON, small fixture (wiring proven)
- Path B: 26/28 probe checks PASS (UI flow works)

What I have NOT verified:
- Path C: bypass OFF, realistic fixture (real pipeline unverified)
- Path D: production-shape map with real images (untested)

Ask the operator: which verification path should I take next?
```

This is the SPECIFIC shape of "I am not done yet." Operators can scan it in 5 seconds and direct the next step. The "26/28 PASS, goal complete" frame I used in the previous turn obscured exactly this information.

### When this discipline DOESN'T apply

- **Trivial fixes** (typo corrections, formatting changes, doc updates) — verification is "the diff compiles and tests pass."
- **Single-path fixes** where there's only one way to verify (e.g. a unit test that's deterministic).
- **Production-only fixes** where dev/staging verification is impossible.

The rule applies specifically when:
- Multiple verification paths exist (bypass vs. real pipeline, mock vs. live integration, unit vs. end-to-end).
- The "success" path is one of several possible paths, not the canonical one.
- The operator's intended deployment shape (production, demo, etc.) determines which path matters.

### Pitfall 13 — Claiming "goal complete" while a code path was only verified through a permissive bypass (added 2026-08-12)

**Symptom**: Operator reads "26/28 PASS, all visually verified, screenshots saved" and trusts the fix shipped. A week later, in production or staging with no bypass, the same code path fails with a different error because the REAL pipeline (not the bypass) was never exercised.

**Fix**: Always separate "what I verified" into multiple paths and mark each. Bypass-ON verification is a real check — it proves the wiring — but it does NOT prove the production code path. Both must pass before claiming completion.

**Empirical 2026-08-12 cost**: The operator's push-back on "26/28 PASS" led to a 5-10 minute debugging detour (BYPASS confirmation → live-safety verification with `DEV_SAFETY_LIVE_TEST=1` → trace dissection → 30-second Bedrock round-trip → real LLM rejection reason captured in trace). All of this was necessary BECAUSE the original completion claim was premature.

**Reference**: this section was added to the skill 2026-08-12 in response to that exact failure mode.