---
name: tpipe-pipe-feature-audit
description: |
  Methodology for auditing pipe-level cross-cutting features in TPipe — features that should affect both the main pipe and its reasoning pipe but may silently no-op because the propagation path is broken. Use when investigating whether a setting (service tier, caching, guardrail, region, timeout, etc.) actually reaches the wire for the pipes you think it does. ALSO USE on "is feature X enabled for pipe Y?" and "why didn't my tier/cache/guardrail setting take effect?" The Flex-tier eligibility audit on Autogenesis's qwen235B agents is the canonical SINK-side case study. ALSO USE when WIRING a new SDK Converse field across the 14 `build*ConverseRequest` builders + the `BedrockMultimodalPipe` delegate path — the SOURCE-side companion. Task 3 `performanceConfig` wire on `bedrock-sdk-1.6.107-upgrade` is the canonical SOURCE-side worked example. Load when investigating tier/cache/guardrail/region/timeout propagation, or when adding a new `applyX()` cross-cutting extension.
version: 2.0.0
metadata:
  hermes:
    tags: [tpipe, pipe, audit, feature-propagation, tier, caching, guardrails, silent-no-op, cross-cutting, bedrock-sdk, wiring, streaming-observer, stall-detector, cross-provider, parity, error-mapping, stop-reason]
    related_skills: [tpipe-pipe-internals, tpipe-context-pull-builder-repair, tpipe-reasoning-pipes]
---

# TPipe Pipe-Feature Audit

## Changelog

- **1.1.0 (2026-07-27)** — Added four pitfalls covering the Bedrock SDK upgrade audit pattern:
  1. "Provider-SDK response events are silently dropped when not subscribed" — the response-side cousin of the dead-builder pitfall. `executeConverseStream` handles 4 of 9+ `ConverseStreamResponse` events; the response-side `ContentBlock` dispatch in `BedrockMultimodalPipe.kt:357` drops everything except Text/Image/Document via the `else -> trace(unknownContentBlockType)` branch.
  2. "`toStreamRequest()` drops guardrail policy fields on the streaming path" — the `ConverseRequest.toStreamRequest()` extension at `BedrockPipe.kt:2641-2647` forwards only `guardrailIdentifier` / `version` / `trace` into `GuardrailStreamConfiguration`, silently dropping content filters, sensitive-info, topic/word, contextual grounding, and automated reasoning policy enforcement on every streaming call.
  3. "Bedrock Mantle is NOT a Bedrock SDK feature — route through `GenericOpenAIPipe`" — Mantle is an OpenAI-compatible endpoint with NO `aws.sdk.kotlin:bedrockmantle` artifact. Future sessions adding Mantle support must route via `GenericOpenAIPipe` with a swapped `baseUrl`, not edit `BedrockPipe.kt`.
  4. "`setJsonOutput()` prompt-injection vs SDK-native `outputConfig.jsonSchema` are incompatible when both are active" — the three concrete failure modes (double-prompting token waste, PCP-merged-mode text-encoded tool-call break, downstream parser contract change) and the feature-flag mitigation pattern.

  - Added `references/2026-07-27-bedrock-sdk-upgrade-consequences.md` as a worked reference.
- **1.2.0 (2026-07-28)** — Added the "Wiring a new SDK Converse field (the SOURCE side)" section covering the complement of the audit methodology: when a NEW Converse field lands in aws-sdk-kotlin, what the multi-site wire pattern looks like. Five concrete gotchas captured during the Task 3 (`performanceConfig`) wire on `bedrock-sdk-1.6.107-upgrade`:
  1. `ConverseRequest.copy(...)` takes a builder lambda, not named parameters — `copy { performanceConfig = cfg }` not `copy(performanceConfig = cfg)`.
  2. The 14-builder + 1-multimodal wire pattern: private/protected `ConverseRequest.Builder.applyX()` extension called from every `build*ConverseRequest`, positioned after `serviceTier = ServiceTier { ... }` and before `applyGuardrailConfig()`.
  3. The `BedrockMultimodalPipe` delegate pattern: when a multimodal pipe does NOT build `ConverseRequest` directly (it uses `when { ... build*ConverseRequest(...) ... }` on the parent), wire is inherited automatically through the parent builders. Verification gates that demand an explicit callsite in the multimodal pipe get a `protected fun applyX(converseRequest: ConverseRequest): ConverseRequest` helper on the parent that returns a copy with the field applied.
  4. The `PerformanceConfiguration` wrapper vs `PerformanceConfigLatency` enum distinction: `getPerformanceConfig()` returns the wrapper, tests must assert `.latency` on the wrapped object, not the wrapper itself.
  5. The `@Suppress`-prohibition: when the plan forbids silencing "unused private extension" warnings, a missing callsite is the bug — add the callsite, do not suppress.
  Added `references/2026-07-28-bedrock-sdk-upgrade-wiring-source-side.md` as a worked reference.
- **1.3.0 (2026-07-28)** — Added `references/2026-07-28-bedrock-sdk-upgrade-sink-side-streaming-event-wire.md` as the worked SINK-side fix for the "Provider-SDK response events are silently dropped" pitfall. Captures the Task 7 wire (ContentBlockStart/ToolUse Start + Delta/Stop + MessageStart handlers + `BedrockCallMetadata` population) and the seven concrete gotchas hit on the `bedrock-sdk-1.6.107-upgrade` branch:
  1. Streaming event constructors live on `ConverseStreamOutput`, NOT `ConverseStreamResponse` — the latter is just the wrapper holding `stream: Flow<ConverseStreamOutput>`.
  2. `MessageStartEvent.role` is `ConversationRole` (SDK enum), not `String` — `role = ConversationRole.Assistant`, not `role = "assistant"`.
  3. `contentBlockIndex` on Start/Stop/Delta events is non-nullable `Int` — `?: 0` elvis emits warnings (the elvis is dead code).
  4. `Document` is abstract; concrete subclasses are `Document$String` etc. — use `document.asString()` / `.asStringOrNull()`, not `.asStringNode()`. Constructor is `Document(stringValue)` (top-level factory), not `Document.fromString(...)`.
  5. `BedrockRuntimeClient` is a Kotlin interface — fake it by implementing the interface directly. `listAsyncInvokes` takes a single arg (no `limit: Int?`), `close(): Unit` is non-suspend (not suspend), `config` is a property getter.
  6. The `toConverseRequestForTest()` seam reverse-map must be field-symmetric with the production `toStreamRequest()` forward-map — every field `toStreamRequest` writes must be read back.
  7. The `internal suspend fun executeConverseStreamForTest(client, ...)` seam is the right pattern when the test needs to inject a client parameter; the existing `private class TestBedrockPipe : BedrockPipe()` subclass pattern is the right pattern when only protected member exposure is needed. Both can coexist.
- **1.4.0 (2026-07-28)** — Added `references/2026-07-28-bedrock-sdk-1.6.107-citation-reassembly.md` as the SINK-side variant for streaming-fragment reassembly into typed objects (the response-side cousin of event subscription). Captures the citation-reassembly wire that closes the Task 8/9 deferred TODO: `BedrockCallMetadata.citations: List<Citation>` is now populated on both streaming and non-streaming paths. Records AWS's actual streaming semantic (one Citation per block, last-non-null wins on metadata, sourceContent.text fragments concatenate) which contradicts the plan's initial "defensive 2 Citations" assumption; the test pins the real contract. Three plan-time Pitfall 12 paraphrasing errors (gotcha 1-3): `asCitationsContentOrNull()` → real name `asCitationOrNull()`, `Citation.sourceContent: List<CitationGeneratedContent>` → real type `List<CitationSourceContent>`, `InvokeGuardrailChecksRequest` body wrapped in `GuardrailContentBlock.Text(GuardrailTextBlock)` → real shape `messages: List<GuardrailChecksMessage>`. Gotcha 4: `BedrockMultimodalPipe.bedrockClient` must be `internal` (not `protected`) for same-module test injection of a subclass-inherited field — sister gotcha to the Task 7 `BedrockPipe.bedrockClient` decision. Gotcha 5: when a subagent discovers a behavioral discrepancy between plan and SDK semantics, rewrite the test to pin the correct behavior AND note the deviation in the report-back — Task 5's subagent did the right thing by renaming `twoDeltasWithDifferentMetadataProduceTwoCitations` to `twoDeltasWithDifferentMetadataCollapsesToLastNonNull` and changing the assertion from `size == 2` to `size == 1`. (`references/2026-07-28-bedrock-sdk-upgrade-sink-side-streaming-event-wire.md` covers the event-subscription SINK side; this one covers the fragment-reassembly SINK side; both fall under "response-side silent-no-op" but at different layers.)
- **1.5.0 (2026-07-29)** — Added pitfall "OpenAI-compatible providers can deviate from the canonical OpenAI event-name wire format" and its worked reference `references/2026-07-29-bedrock-mantle-streaming-reasoning-round3.md`. Captured from the Mantle Round 3 fix (`bedrock-sdk-1.6.107-upgrade` branch): Mantle's `/v1/responses` SSE stream emits `response.reasoning.delta` and `response.reasoning.done` (no `_text` infix) instead of OpenAI proper's `response.reasoning_text.delta` / `…_done`. The existing `OpenAIResponsesSseParser.parseLine` dispatch only knew the long-form names, so Mantle's reasoning deltas fell through to `Unknown` and `streamingReasoningText` was silently never populated — even though the SSE wire delivered every reasoning fragment correctly. Companion pitfall to the streaming-event-drop and `toStreamRequest()` drop patterns already in this skill: same shape (documented contract silent about a sibling), different layer (provider-side wire-format deviation, not SDK-side field omission). The reference captures the full Round 3 fix: the parser dispatch widening (`response.reasoning.delta` / `.done` added as Mantle aliases), the Round 3 signature widening on `executeStreaming(...)` and `executeStreamingDirect(...)` from `String` to `MultimodalContent`, and the matching caller unwraps. Six gotchas from this session are in the reference (parser dispatch was insufficient on its own; the Round 3 signature widening was necessary but insufficient without the parser fix; Round 2's `generateTextMultimodal` helper was the precedent for the Round 3 pattern; the Ktor path goes through `executeStreaming` not `executeStreamingDirect` when env SigV4 is in use; the verifier must use JUnit XML as the authoritative signal for class-level pass counts because gradle stdout drops `PASSED` markers when tests produce heavy stdout; the new test method name `testMantleResponsesStreamingWithReasoning` has underscores that broke the regex `[A-Za-z]+` and demanded `[A-Za-z_]+`).
- **1.6.0 (2026-07-30)** — Added `references/2026-07-30-cross-repo-streaming-parity-triage.md`. Cross-repo triage methodology for cross-cutting features that span SDK and consumer repos (streaming, citations, guardrails, prompt caching). The four-cell gap matrix (prim / wire / test × SDK / consumer) separates work by repo. Three pitfalls: (1) live tests that pass `setStreamingEnabled(true)` and assert text content do NOT verify callback delivery — the wire-content path is independent of the callback delivery path; (2) the Bedrock `streamingCallbacks { add(...) }` builder DSL is not portable to Mantle — `GenericOpenAIPipe` has only single-callback, so consumer code must dispatch on pipe type; (3) `setStreamingEnabled(true)` without a callback is a silent no-op — the pipe runs in streaming mode but no listener catches the chunks, and there is no error signal. Worked example: the 2026-07-30 Mantle streaming triage on Autogenesis where 7 of 8 LOW agents had zero `setStreamingCallback` calls and the orchestrator's `enableBufferedNarrativeStreaming(throttler)` was typed `BedrockPipe` receiver only. Captures the two-repo handoff semantics: SDK side verdict = "complete" if all three SDK cells have passing tests that exercise callback delivery; consumer side verdict is independent.
- **1.7.0 (2026-08-02)** — Added `references/2026-08-02-streaming-stall-detector-audit.md`. The stall detector (TPipe main, 8 commits landed 2026-08-02) is the canonical worked example of a **streaming-observer feature** — a pipe-level cross-cutting concern that fires not on a wire signal but on statistics of the wire signal. Extends the five-path wire-reach recipe to six paths: any feature that observes the chunk stream must satisfy the existing five paths AND a sixth path (the streaming callback manager chain) — without it the detector is silent. Captures eight pitfalls hit on the audit: (1) `enableStallDetector` without `streamingEnabled=true` is a silent no-op; (2) the conjunctive trigger is `max(mean + kσ, stallMinSilenceMs)` not `mean + kσ + stallMinSilenceMs` — both paths matter; (3) population variance (divide by N) not sample variance — the detector is a streaming classifier, not a statistical estimator; (4) first token early-return guards against the spurious ~16M-ms first interval on a 1970-epoch timestamp; (5) `StallCallback` is suspend + fired via GlobalScope + failures swallowed — callback cannot return a retry decision; (6) `handleStallSignal` uses a separate `stallRetryAttempts` counter (not `retryAttempts`) — sharing conflates two independently-tunable budgets; (7) `activeStallDetector` lifecycle is "set on enter, clear on abort, clear in finally" — the same triple as `activeJob`; (8) pipeline-level propagation is config-only, not state — each pipe owns its own `StreamingStallDetector` since per-pipe stats need per-pipe state, deliberately different from `enablePipeTimeout`/`applyTimeoutRecursively` which DO recursively cascade. The 6-check verification recipe is at the bottom of the reference.
- **1.7.1 (2026-08-02, verification pass)** — Added the TPipe multi-project Gradle `:test` path gotcha to `references/2026-08-02-streaming-stall-detector-audit.md` and JUnit-XML-based pass-count recipe. The plan file at `.hermes/plans/streaming-stall-detector.md` (Task 8, all Step 4 gradle invocations) says `./gradlew :TPipe:test` — this fails with `Project 'TPipe' is ambiguous in root project 'TPipe'. Candidates are: TPipe-Bedrock, TPipe-Defaults, ...` because TPipe is a multi-project Gradle build where the **root project** holds the stall-detector source and the **subprojects** are the provider modules. Correct path: `./gradlew :test --tests "..."` (root only) or `./gradlew test --tests "..."` (root + all subprojects — works but TPipe-Tuner has no matching tests and fails the filter). Bare `:TPipe:test` is wrong; the `:test` (root) form is right. The pass-count recipe parses `build/test-results/*Stall*.xml` directly because gradle stdout drops `PASSED` markers when tests produce heavy stdout (already documented in 1.5.0 changelog for the Mantle Round 3 case).
- **1.8.0 (2026-08-02)** — Added the **Cross-provider feature parity audit** methodology as a sibling framework to the SINK/SOURCE five-path recipe (which audits ONE feature across propagation paths WITHIN one provider). The cross-provider audit asks: does feature X behave consistently across all provider modules? Dimensions: **stop-reason capture**, **connection-drop handling**, **error → P2PException propagation**, **tracing hookup**. Each dimension is a binary per-provider check, producing a 4×N scorecard. Work order: sort by completeness (tracing-only → tracing+partial-errors → tracing+full), then fix from lowest to highest. Worked reference `references/2026-08-02-provider-feature-parity-breakdown.md` captures the 2026-08-02 audit of all 5 TPipe-* modules (Bedrock, GenericOpenAI, Ollama, OpenRouter, MCP). Headline findings: GenericOpenAI is the only fully-connected provider; Bedrock has zero P2PException mapping; Ollama has no retry and no error mapping; OpenRouter has zero `finish_reason` capture and `abort()` nulls the HTTP client (the previously-fixed GenericOpenAI bug shape). Three new pitfalls captured: **(1)** "OpenRouter-style `abort() = null` is the same shape as the previously-fixed GenericOpenAI bug — call it out, don't ship it"; **(2)** "stop-reason capture is independent of error mapping — a provider can have perfect tracing and perfect P2PException wrapping while still emitting no `finish_reason` into metadata"; **(3)** "MCP is a bridge, not a provider — it has zero `trace()` calls by design; don't count it in parity scorecards or it will look broken".
- **1.9.0 (2026-08-08)** — Added the **Cross-container feature parity audit** methodology as a second sibling to the cross-provider audit. Same shape (N-row scorecard of feature × container), different layer (TPipe's orchestration containers instead of LLM provider modules). Trigger: when a `TraceConfig` field (or any class-level feature surfaced via DSL builders) is honored by some containers and silently ignored by others. The 2026-08-08 audit confirmed the operator's `autoExport` example: `TraceConfig.autoExport` + `exportPath` honored by 2 of 6 containers (Pipeline, PumpStation), silently ignored by 4 (Manifold, Splitter, Junction, DistributionGrid). Added pitfall "When a contract has both a configuration site AND a builder site, also enumerate the consumer sites — the number of consumer sites IS the parity scorecard". Added `references/2026-08-08-trace-config-cross-container-parity.md` capturing the full 2026-08-08 audit: 5 dead private fields (PumpStation.maxConcurrentAgents / parentTokenBudgetSettings / truncationSettings; Splitter.isExecuting; HttpSecurityManager.privateNetworkRanges with 8 CIDRs ignored), 11 interface no-op stubs in P2PInterface (compiler-not-enforcing contract), 13 emitted-but-unconsumed trace events (especially `KILLSWITCH_TRIPPED`), 2 declared-but-unemitted events (`PAUSE_POINT_CHECK`, `PIPE_TIMEOUT`), ~10 dead function parameters (`setJsonInput`/`setJsonOutput`/`setValidatorPipe` ignoring their inputs at Pipe.kt:2941, 2995, 4859), plus the malformed filename at `Pipeline.kt:873` (literal extension token embedded in middle of name = clear signal the autoExport path was never run end-to-end).
- **2.0.0 (2026-08-08)** — Bumped to 2.0.0 because the skill scope expanded beyond pipe-feature-audit into a general **trace-config parity audit methodology** with three new pillars: (1) the operator's "narrow to TraceConfig" mid-session correction captured as the **scope-narrowing workflow rule** — when the operator says "narrow to X" mid-investigation, drop everything else and re-run the search scoped to X; the original ask was an audit, the narrowed ask is the real surface. (2) The **thread-safe autoExport closure** added as `references/2026-08-08-trace-config-autoexport-tdd-closure.md` — the canonical worked FIX-side example for when the fix introduces a concurrency surface (writing to disk from a synchronous `getTraceReport()` that multiple containers can call). Includes the `TraceAutoExporter` design (per-path `ReentrantLock` map, hard-deadlock-free by construction: no nested locks, lock held only for the write closure, never re-entered by user code), 4 thread-safety tests (concurrent same-path = serialize; concurrent different-paths = parallel; no corruption under contention; no indefinite block), the missing-API additions (`getTraceId` on DistributionGrid + MultiConnector; `getTraceReport` on Connector + MultiConnector; `setRunIdForTest` on PumpStation), and the malformed-filename regression at `Pipeline.kt:873`. (3) The **test-seam taxonomy** added to the closing-with-TDD section: reader seam (`internal fun getXxxForTest(): T`) for "field was set" assertions; ID seam (test setter to inject deterministic runId/gridId) for "container used the right id" assertions; producer seam (a public method on the container that the test can call without reconstructing internal state) for "container produced an output" assertions. Plus the **doc-claim contradiction pattern**: when the operator-facing doc states the contract is broken (e.g. `docs/core-concepts/tracing-and-debugging.md:90` literally saying `autoExport` "is not used by the actual tracing system"), the doc is part of the fix surface — leaving it stale after a successful fix means the next operator skips the feature. New pitfalls added: "When the operator says 'narrow to X', drop everything else and re-scope"; "Thread-safe auto-export: per-path mutex is the right shape"; "Test-seam taxonomy for read-side parity audits"; "Malformed-filename bug is a 'this code path was never run' tell"; "Doc claims that contradict the implementation are part of the fix surface". New section "Closing a thread-safe auto-export parity gap with TDD" added at the end of the closing-with-TDD recipe.

## When to load

Load this skill whenever the user asks a question of the shape:

- "Is feature X applied to pipe Y?"
- "Why didn't my tier / cache / guardrail setting take effect on pipe Y?"
- "Which pipes in this codebase actually get feature X?"
- "Audit pipe-level feature X across the codebase"
- "I set feature X but I don't see it on the wire"
- "If we bump the provider SDK (aws-sdk-kotlin, openai-java, ollama), what new provider features can we use, and what changes on our wire surface?"
- "How do we wire feature X (structured output, citations, latency capture, tool calls in streaming) from the SDK response into our `MultimodalContent`?"
- "The model returned citations / tool calls / guard assessments in the stream — how do I harvest them into `BedrockCallMetadata`?"
- "Do providers X and Y handle stop reasons the same way?"
- "Which providers wrap errors as `P2PException` and which throw raw?"
- "Audit provider-level parity for feature X (stop reason / connection drop / error mapping / tracing) across all `TPipe-*` modules"
- "Audit container-level parity for feature X across Pipeline / PumpStation / Manifold / Splitter / Junction / DistributionGrid"
- "I set `tracing { autoExport(true) }` on my Manifold but nothing writes to disk — is autoExport wired?"
- "Why is container N ignoring config X even though I see it on the DSL?"

The class-level signal is any pipe-level feature that has both a setter on `Pipe` (or `BedrockPipe`, `OpenRouterPipe`, `GenericOpenAIPipe`, `OllamaPipe`) AND independent state on the reasoning pipe. The flex-tier audit on AWS Bedrock is the worked example; the same audit shape applies to:

| Feature | Main pipe owner | Reasoning pipe owner | Where it could propagate wrong |
|---|---|---|---|
| Service tier (`setServiceTier`) | `BedrockPipe.serviceTier` | Same field on the reasoning pipe (a separate `BedrockMultimodalPipe`) | `setReasoningPipe()` does NOT carry over. The reasoning pipe has its own private state. |
| Prompt caching | `BedrockPipe.cacheControl` | Separate field on reasoning pipe | Same boundary |
| Region | `BedrockPipe.region` | Separate field on reasoning pipe | Same boundary; main pipe init reads one region, reasoning pipe init may read another |
| Read timeout | `BedrockPipe.readTimeoutSeconds` | Separate field on reasoning pipe | Same boundary |
| Guardrail | `BedrockPipe.guardrailIdentifier` / `guardrailVersion` / `guardrailTrace` | Separate fields on reasoning pipe | Same boundary |
| Citations (streaming) | `BedrockPipe.collectedCitations` accumulator | N/A — only the main pipe emits citations | The streaming delta handler in `executeConverseStream` |
| Service tier via `serviceTier` on OpenRouterConfiguration | Stored on the config dataclass | **Not** propagated to reasoning pipe's `OpenRouterPipe` automatically | The `OpenRouterDefaults` factory reads `config.serviceTier?.let { setServiceTier(it) }` — only the pipe being built at that moment gets the tier, not its future reasoning pipe |

## The five wire paths a pipe-level feature travels

When auditing a feature, trace it through all five paths. A feature that is wired on three of the five and missing on the remaining two silently no-ops for those two surfaces.

1. **The main pipe** (`BedrockPipe` / `OpenRouterPipe` / `GenericOpenAIPipe` / `OllamaPipe`). The pipe that issues the actual user-facing API call. State lives on this pipe.

2. **The reasoning pipe** (the inner pipe attached via `setReasoningPipe(...)`). Has its own state, separate from the main pipe. `setReasoningPipe()` does not copy any property from the parent — only the system prompt, JSON output, and DITL hooks are wired by `ReasoningBuilder.assignDefaults()`.

3. **`PipeSettings`** (`TPipe/src/main/kotlin/Structs/PipeSettings.kt`). A snapshot dataclass that survives serialization. `applyPipeSettings(...)` writes snapshot fields onto a pipe. If the feature is not a field on `PipeSettings`, you cannot round-trip it across `toPipeSettings()` / `applyPipeSettings()`.

4. **`ProviderConfiguration` subclasses** (`TPipe-Defaults/.../ProviderConfiguration.kt`). Typed configuration objects passed to `createXxxPipe(config)` factories. If the feature is not a field on the relevant `XxxConfiguration`, you cannot declare it at factory-call time — you must call the setter on the returned pipe.

5. **Runtime overrides** (e.g. `gameplayOrchestrator.kt` retry-swap that calls `pipe.setModel(...)` / `pipe.setTokenBudget(...)` / `pipe.disableReasoning()` mid-execution). Any property NOT explicitly re-set in the override inherits from the prior pipe state. If the original pipe's feature was never set, neither is the override's.

The audit recipe is: for each pipe in scope, check the state of each of the five paths. If any path is empty/missing, document that the feature is invisible on that surface.

## The four-pass audit methodology

### Pass 1 — locate the feature on the provider class

Start at the provider's `Pipe` subclass. For Bedrock: `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt`.

For each candidate feature:

- Where is the field declared? (`private var serviceTier: BedrockPriorityTier = BedrockPriorityTier.Standard`)
- What is the default? (Almost always the cheapest / safest / Standard tier — the user must opt in.)
- Where is the setter? (A `fun setX(...)` method that writes the field and returns `this` for chaining.)
- Where does the field reach the wire? (Inside `mapServiceTier()` for tier; analogous helper for other features.)
- Where is `mapServiceTier()` invoked? (Every call site of `ServiceTier { type = mapServiceTier() }` is one path where the tier reaches the wire.)

If the feature has NO field on the provider pipe, it is impossible for that provider to carry it — move on.

### Pass 2 — confirm Defaults dataclasses do not silently carry it

Check whether the feature has a field on the relevant `XxxConfiguration` (`ProviderConfiguration.kt`). If it does, check the corresponding `XxxDefaults.createXxxPipe(...)` factory for whether it reads the field. If it does NOT, the configuration surface is silent — callers cannot opt in via the typed config object.

For tier specifically: `BedrockConfiguration` (line 71) has no `serviceTier` field. `OpenRouterConfiguration` (line 224) has `var serviceTier: String? = null` and `OpenRouterDefaults.createOpenRouterPipe` (line 89 of `OpenRouterDefaults.kt`) reads it via `config.serviceTier?.let { setServiceTier(it) }`. This is the only Defaults dataclass with a tier field. **No Bedrock defaults path can declare a tier declaratively** — you must call `pipe.setServiceTier(BedrockPriorityTier.Flex)` on the returned pipe.

### Pass 3 — confirm PipeSettings does not silently carry it

`PipeSettings` (`Structs/PipeSettings.kt:20-72`) is the serialization-safe snapshot. If the feature is not a field on `PipeSettings`, the feature cannot survive `toPipeSettings()` / `applyPipeSettings()` round-trips. For tier: `PipeSettings` has no tier field. For OpenRouter-specific tier, this is a real gap — `OpenRouterConfiguration.serviceTier` is set declaratively but `PipeSettings.serviceTier` is missing, so a reasoning pipe built with a tier-specified OpenRouter config but no manual `setServiceTier(...)` call on the pipe will lose the tier after any serialization round-trip.

### Pass 4 — enumerate every pipe that consumes the feature

Run a grep across the consuming codebase. For tier on Bedrock:

```bash
grep -rn "setServiceTier\|useFlex" path/to/agent/builders
```

Classify each match by:

- **Pipe role**: main pipe / reasoning pipe / branch pipe / retry-swap / validator pipe.
- **Setter state**: active call, commented-out (`// setServiceTier(Flex)`), or absent.
- **Comment context**: is the commented-out line sitting next to a `setModel(...)` that names a model known to support the feature? If yes, the original developer drafted the feature and rolled it back.

For every match, classify the `setJsonOutput` target (or absence of it) into one of:

- **ELIGIBLE** — small structured output (enums, bools, lists of identifiers, short scoring records). Feature is appropriate here.
- **NARRATIVE** — large free-text or world-object output (story chapter, NPC character, resource grant description). Feature is the wrong tool — latency cost dominates.
- **REASONING** — actually a reasoning pipe (look for `setReasoningPipe(...)` inside a builder). Tier is governed by the factory's `useFlex` flag, not by the main pipe's setter.
- **RETRY-SWAP** — runtime override inside a loop. Inherits prior pipe state.

For Flex-tier on Bedrock, the rubric and worked classification for the Autogenesis codebase lives at `references/2026-07-25-autogenesis-flex-tier-eligibility.md`.

### Pass 5 — cross-check the `setReasoningPipe` boundary

For every main pipe that consumes the feature, find its `setReasoningPipe(...)` call. Check whether the inner reasoning pipe has its own setter for the feature. If yes, the inner pipe's state is independent and must be set separately.

For tier: every `BedrockConfig.structuredCotBuilder(...)` / `explicitCotBuilder(...)` / `processFocusedBuilder(...)` / `bestIdeaBuilder(...)` / `obsessivePlannerBuilder(...)` / `authorBuilder(...)` accepts a `useFlex: Boolean = false` parameter. When true, it calls `pipe.setServiceTier(BedrockPriorityTier.Flex)` on the reasoning pipe. This is the Autogenesis-specific escape hatch for reasoning-pipe tier propagation — separate from the main pipe's setter.

If every Autogenesis call site for qwen235B reasoning pipes passes `useFlex = false` (explicitly or by default), the reasoning pipe runs on Standard regardless of the main pipe's tier.

## Cross-provider feature parity audit (the COMPARE side)

The five-path recipe audits ONE feature across propagation paths WITHIN one provider. The cross-provider audit asks the orthogonal question: does a feature behave consistently across ALL provider modules?

This is its own framework, not a derivative of the five-path recipe. The dimensions and the binary per-provider check make a 4×N scorecard (4 audit dimensions × N provider modules), which is what an operator wants when they say "audit stop reasons / connection drops / errors / tracing across all providers."

### The four dimensions

For every provider module in scope (typically the 5 TPipe-* modules: TPipe-Bedrock, TPipe-GenericOpenAI, TPipe-Ollama, TPipe-OpenRouter, TPipe-MCP), score each dimension as ✅ / ⚠️ / ❌:

| Dimension | ✅ Full | ⚠️ Partial | ❌ Absent |
|---|---|---|---|
| **Stop-reason capture** | Stop reason from every wire shape (Invoke + Converse + ConverseStream for Bedrock; OpenAI Chat + Responses + Anthropic for GenericOpenAI) flows into `metadata["stopReason"]` AND into a typed field | Stop reason captured in some paths, missing in others (e.g. only streaming, not non-streaming) | No read of `stop_reason` / `finish_reason` anywhere |
| **Connection-drop handling** | Custom retry/reconnect OR provider-SDK-level recovery that survives mid-stream blips | Read-timeout configured but no retry | Bare `HttpClient` per call, single-attempt, throws on failure |
| **Error → P2PException propagation** | Every `HttpRequestTimeoutException / SocketTimeoutException / ConnectException` (and provider SDK error envelopes) maps to `P2PException(P2PError.transport / auth / prompt / json, …)` | Maps SOME exception types but not others; SSE mid-stream errors leak as raw `IOException` | Caught and rethrown raw with no P2P wrapping |
| **Tracing hookup** | `trace(TraceEventType.PIPE_* / API_CALL_*)` at every boundary including success, failure, and validation | Tracing on success but not failure (or vice versa) | No `trace()` calls |

### The audit recipe

```bash
# 1. Locate stop-reason reads across all providers
search_files 'stop_reason|stopReason|finish_reason|finishReason|message_stop|end_turn' \
  --target content \
  --path TPipe-Bedrock/src/main/kotlin/bedrockPipe \
  TPipe-Ollama/src/main/kotlin/ollamaPipe \
  TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe \
  TPipe-OpenRouter/src/main/kotlin/openrouterPipe

# 2. Locate connection-drop + retry handling
search_files 'runRequestWithRetry|retry|HttpRequestRetry|reconnect' \
  --target content --path TPipe-*/src/main/kotlin

# 3. Locate error → P2PException mapping
search_files 'P2PException|HttpRequestTimeoutException|SocketTimeoutException|ConnectException' \
  --target content --path TPipe-*/src/main/kotlin

# 4. Locate tracing hookups
search_files 'trace\(TraceEventType' \
  --target content --path TPipe-*/src/main/kotlin
```

Each search returns a `total_count` per provider. Compare against expected:
- Bedrock: ≥ 50 trace sites, 4+ P2PException mappings (typically 0 — that's the audit finding)
- GenericOpenAI: ≥ 15 trace sites, ≥ 3 P2PException mappings
- Ollama: ≥ 15 trace sites, 0 P2PException mappings (typically)
- OpenRouter: ≥ 5 trace sites, ≥ 3 P2PException mappings
- MCP: 0 trace sites, 0 P2PException mappings (bridge, not a provider — exclude from parity scorecard)

### Work order

Sort the scorecard by completeness (tracing-only → tracing+partial-errors → tracing+full). Fix from lowest to highest. The lowest-completeness providers are the ones operators will hit first when their production traffic fails: Bedrock is the worst because transport errors there never reach the P2P routing layer.

The 2026-08-02 worked example (4 dimensions × 4 LLM providers, excluding MCP) produced this exact sort order:

1. **OpenRouter** (tracing + partial P2P, no finish_reason, no retry) — 4 fixes
2. **Ollama** (tracing + stop-reason, no P2P, no retry) — 2 fixes
3. **Bedrock** (tracing + stop-reason, no P2P) — 1 wide fix
4. **GenericOpenAI** (everything) — 0 fixes (reference implementation)

### Verification recipe after fixes

After each fix, re-run the grep queries and confirm the cell flipped from ❌/⚠️ to ✅. The scorecard IS the verification artifact — don't file a "completed" report without the updated scorecard.

```bash
# Re-score after fixes
search_files 'P2PException' --target content --path TPipe-Bedrock/src/main/kotlin/bedrockPipe
# Expected: ≥ 3 new matches at the catch sites that previously rethrew raw
```

### What this is NOT

- **Not a substitute for the five-path recipe.** Use that for "does feature X reach the wire within ONE provider?" Use this for "does feature X behave consistently across providers?"
- **Not a code-coverage metric.** A provider can have 60 trace sites and still fail this audit if its P2PException mapping is missing.
- **Not a substitute for cross-repo triage.** If the same feature spans SDK + consumer repos (e.g. streaming callbacks), use `references/2026-07-30-cross-repo-streaming-parity-triage.md` instead.

The full worked audit (Bedrock, GenericOpenAI, Ollama, OpenRouter, MCP) is at `references/2026-08-02-provider-feature-parity-breakdown.md`.

## Cross-container feature parity audit (the SECOND COMPARE side)

The cross-provider audit above asks "does feature X behave consistently across provider modules?" The cross-container audit is structurally identical but scopes to TPipe's orchestration containers: Pipeline / PumpStation / Manifold / Splitter / Junction / DistributionGrid. Same N-row scorecard, different layer.

### When to use this audit

The trigger is: a feature has both a configuration site (a field on a `XxxConfig` data class, e.g. `TraceConfig.autoExport`) AND a builder site (a DSL method on `XxxTracingDsl` / `TracingBuilder`), AND there's no compiler or test signal that flags "container N ignored the contract." When that shape exists, the contract looks complete from the caller's perspective but is silently ignored by some implementations.

### The audit recipe

For every container in scope, find every read site of the feature's field. A single `grep` enumerates the consumer surface; the count of consumers IS the parity scorecard.

```bash
# Find every consumer of TraceConfig.autoExport
search_files 'autoExport' --target content --path src/main/kotlin/Pipeline
# Returns: Pipeline.kt (✓), PumpStation.kt (✓), Manifold.kt (✗), Splitter.kt (✗),
#          Junction.kt (✗), DistributionGrid.kt (✗), TraceConfig.kt (declaration),
#          TracingBuilder.kt + PumpStationDsl.kt (builders)
# Scorecard: 2 of 6 containers honor the contract.
```

A parity scorecard is the verification artifact — don't file a "completed" report without the updated scorecard.

### Worked example: TraceConfig.autoExport

`TraceConfig.autoExport` and `TraceConfig.exportPath` are declared in `Debug/TraceConfig.kt:19-20`, surfaced via `TracingBuilder.autoExport()` and `PumpStationTracingDsl.autoExport()`, and honored by 2 of 6 containers:

| Container | getTraceReport location | autoExport honored? |
|---|---|---|
| `Pipeline` | `Pipeline.kt:860-879` | ✅ Yes |
| `PumpStation` | `PumpStation.kt:2815-2838` | ✅ Yes |
| `Manifold` | `Manifold.kt:2482-2485` | ❌ No — silently returns string |
| `Splitter` | `Splitter.kt:568-571` | ❌ No — silently returns string |
| `Junction` | `Junction.kt:1558-1561` | ❌ No — silently returns string |
| `DistributionGrid` | `DistributionGrid.kt:1208-1211` | ❌ No — silently returns string |

**Symptom**: a user wires `manifold { tracing { autoExport(true, path = "/traces") } }` and gets no file. The DSL accepted the call, the configuration site stored the value, but the consumer side never reads it.

**Fix shape**: replicate the `if(traceConfig.autoExport) { writeStringToFile(...) }` block across the 4 missing containers. ~10 lines per container, identical shape to Pipeline.kt:864-876 with container-specific filename prefix and id-taker length.

**Bonus defect**: Pipeline.kt:873 has a malformed filename — `"trace-${pipelineId.take(8)}-$extension.${extension}"` produces `trace-abc12345-html.html` (literal extension token embedded in the middle). Cosmetic, but a clear sign that the autoExport path was never run end-to-end. Fix to `"trace-${pipelineId.take(8)}.$extension"`.

The full 2026-08-08 audit (5 dead fields, 11 interface no-op stubs, 13 unconsumed trace events, 2 unemitted events, ~10 dead parameters, this filename bug) is captured at `references/2026-08-08-trace-config-cross-container-parity.md`.

### What this is NOT

- **Not a substitute for the cross-provider audit.** Use that for provider modules; use this for orchestration containers.
- **Not a substitute for the five-path recipe.** Use that for "does feature X reach the wire within ONE provider/container?" Use this for "does feature X behave consistently across containers?"
- **Not a substitute for dead-code sweeping.** This audit catches "container N ignored the contract"; a dead-code sweep catches "this field has no read site anywhere." Both are needed — they surface different defects.

### Closing a cross-container parity gap with TDD (the FIX-side recipe)

The cross-container audit surfaces a parity scorecard; the fix-side recipe is how you close the gap without introducing regressions. The 2026-08-08 `maxHistory` close-out is the canonical worked example. Same six-shape pattern that the cross-provider fixes use; same TDD discipline as `test-driven-development`. The recipe has six steps:

**Step 1 — Write the failing test for every container.** One test per container that calls `enableTracing(TraceConfig(maxHistory = N))` and asserts the propagation took effect. For `maxHistory` this was `ContainerMaxHistoryPropagationTest` (9 tests, one per container + one behavioral trim test). The test must fail at every site the audit flagged and pass at the sites that were already wired (Pipeline + PumpStation). A test that passes immediately on the first run tests nothing — see the `test-driven-development` skill's RED-then-GREEN discipline.

**Step 2 — Add a test seam on the production class.** Private state (e.g. `PipeTracer.maxTraceHistory`) cannot be asserted from `src/test/kotlin/` without a public-facing accessor. The cleanest seam: an `internal fun getXxxForTest(): T` next to the existing `setXxx(...)` method, with KDoc explaining that production code does not consume it and that `internal` visibility keeps it out of the public API surface while still being reachable from same-module test code. The seam is the production contract for test access — without it the test has no clean way to verify propagation.

```kotlin
// On the production class:
fun setMaxHistory(max: Int) { maxTraceHistory = max }
internal fun getMaxHistoryForTest(): Int = maxTraceHistory
```

Already-documented precedent for `internal` visibility on test seams: `BedrockMultimodalPipe.bedrockClient` was made `internal` (not `protected`) so same-module tests could inject a subclass-inherited field without changing the public API surface. Same pattern, different field.

**Step 3 — Run the test, confirm RED.** Initial run produces the exact failure pattern the audit predicted: every container the audit flagged fails its test, every already-wired container passes. The failure pattern is the verification artifact that the test is correctly capturing the gap. If the failures don't match the scorecard, the test is wrong — fix the test, not the production code.

**Step 4 — Wire each missing container with the same one-line fix.** The fix shape is identical across all missing sites:

```kotlin
fun enableTracing(config: TraceConfig = TraceConfig(enabled = true)): XxxContainer
{
    this.tracingEnabled = true
    this.traceConfig = config
    PipeTracer.enable() // already present on most
    PipeTracer.setMaxHistory(config.maxHistory) // ADD THIS LINE
    return this
}
```

Patch each missing container individually with surrounding context that makes the location unique — DO NOT use `replace_all=true` because the surrounding `markShellDirty()` / `startTrace(pipelineId)` / branch-propagation blocks differ per container. See `tpipe-pipe-feature-audit` § "TDD's patch discipline for multi-site documentation" for the multi-site `patch` rationale.

**Step 5 — Run the test, confirm GREEN. Then verify with JUnit XML.** Re-run the targeted test class — every test should now pass. For pass-count verification, parse `build/test-results/test/*ContainerMaxHistory*.xml` directly. JUnit XML is authoritative; gradle stdout drops `PASSED` markers when tests produce heavy stdout (already documented in 1.5.0 of this skill for the Mantle Round 3 case). The pass count `tests="N" failures="0" errors="0"` is the verification artifact for the close-out.

**Step 6 — Run the broader test suite for regressions.** Focused suites first (e.g. `com.TTT.Debug.*` if you changed a Debug class, `com.TTT.Pipeline.*` if you changed a container). Full repo run is too slow for verification (~10 min for the TPipe repo) — kill it and rely on focused subsets plus manual regression hunting on the changed file:line sites. JUnit XML is the authoritative signal; tail stdout is decoration.

### Updating the docs that mark the contract as "not used"

When the audit uncovers a documented-but-dead contract (the canonical case: `docs/core-concepts/tracing-and-debugging.md` literally stated `maxHistory` "is not used by the actual tracing system" because the gap was already known), the docs are part of the fix. A `docs/*.md` patch is in scope for parity-gap close-outs because the docs are the operator-facing contract — leaving them wrong after a fix lands means the next operator who reads them skips the feature entirely.

Patch recipe:
1. Identify every doc file that names the now-fixed field as "not used" / "silently dropped" / "dead" / similar language.
2. Replace the dead-claim with the actual contract: which fields ARE honored, which containers honor each, what the consumer-site gap (if any) still is.
3. Reference the audit that surfaced the gap, so future auditors can verify the doc matches the implementation.

A doc that contradicts working code is a bug class of its own — it belongs in the parity audit's reach surface, not just the implementation surface.

## Pitfalls

### Reasoning pipes have independent state — they are not a "view" of the main pipe

The single most common mistake when investigating "feature X is on but not working" is to assume the main pipe's setting propagates to the reasoning pipe. It does not. `setReasoningPipe(reasoningPipe)` wires the reasoning pipe into the parent's `execute()` flow, but no properties are copied. The reasoning pipe owns its own `serviceTier` / `cacheControl` / `region` / `readTimeoutSeconds` / etc. To set a feature on the reasoning pipe, call the setter on the reasoning pipe (either at construction time, via the factory's parameter, or after construction via `reasoningPipe.setX(...)`).

### Defaults factories never carry features they do not have a field for

If the feature is not a field on `XxxConfiguration`, the factory cannot opt in declaratively. Two patterns to fix:

1. Add a field to `XxxConfiguration` and have `createXxxPipe(...)` read it (e.g. `OpenRouterConfiguration.serviceTier`).
2. Add a `useX: Boolean` parameter to the factory (e.g. `authorBuilder(useFlex = false, ...)`) and call the setter when true.

Pattern 2 is what Autogenesis chose for Flex on Bedrock because they did not want to bake tier into the typed config surface (some users want Flex, others want Standard, depending on the calling pipe's role).

### `PipeSettings` round-trip is a separate propagation path

If a feature survives `toPipeSettings()` / `applyPipeSettings()`, it round-trips through serialization (snapshot, debug export, runtime handoff). If it does not, the feature is lost across any serialization boundary. `PipeSettings` currently has no `serviceTier` field — Bedrock tier does NOT round-trip. This is a known gap; if you need tier to survive serialization, add the field to `PipeSettings` AND wire it through both ends.

### `constructPipeFromTemplate(...)` does not copy feature state

`com.TTT.Util.constructPipeFromTemplate<BedrockMultimodalPipe>(...)` is used in branch-pipe repair flows. The helper copies model, budget, region, and a few specific things — but it does NOT copy every property. Specifically, `serviceTier` is reset to default on the templated pipe. If you need a tier on a branch pipe, call `setServiceTier(...)` explicitly after `constructPipeFromTemplate(...)`. Autogenesis's `buildBranchPipeFromTemplate` (BranchFailureAgent.kt:113-132) does this with `setServiceTier(BedrockPriorityTier.Standard)` — clamping to Standard rather than inheriting Flex.

### Runtime retry-swaps inherit prior pipe state

If a runtime retry-swap calls `pipe.setModel(newModel)` and `pipe.setTokenBudget(newBudget)` but does NOT call `pipe.setServiceTier(newTier)`, the tier is whatever the prior pipe had. In `gameplayOrchestrator.kt:2759`, the retry-swap to `qwen235B` does not set tier; the new pipe inherits the Standard default. For the orchestration to actually emit a non-default tier, the originating pipe must have already had the tier set — which it never did on Autogenesis's qwen235B agents.

### Commented-out setters signal "rolled-back intent"

A line like `// setServiceTier(BedrockPriorityTier.Flex)` immediately above `setModel(...)` is a strong signal that:

1. The original developer knew the feature existed and would help here.
2. They drafted the setter but did not merge it.

Do NOT ignore these — they are exactly the sites where the feature will work, with the smallest possible change (uncomment the line). They are also the sites where the developer had a reason to roll back: latency sensitivity, cost concerns, observability gaps, or simply incomplete testing. Before uncommenting, look for the original PR / commit message to understand why it was rolled back.

### "It's set to Flex because the parent was Flex" is a false assumption

Reasoning pipes inherit `setReasoningPipe()` but NOT feature state. The Autogenesis codebase has multiple qwen235B sites where both the main pipe and the reasoning pipe have commented-out `// setServiceTier(Flex)` lines. Without manual uncomment on both sides, neither runs Flex — and uncommenting the main pipe alone still leaves the reasoning pipe on Standard.

### Provider-SDK response events are silently dropped when not subscribed

Every provider SDK exposes a sealed-class stream of response events (streaming deltas, response-side content blocks, metadata frames). Our streaming executor subscribes to a SUBSET of those events. The rest are silently dropped, even though the SDK delivers them on every call. This is the same shape as the dead-builder / silent-no-op pattern, but on the response side: the SDK does fire the event, our code just never asks for it.

The canonical case on Bedrock: `executeConverseStream` at `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:4300` handles exactly 4 of 9+ `ConverseStreamResponse` event types:

| Event | Handled? | What we lose by not subscribing |
|---|---|---|
| `ContentBlockStart` | ❌ | `toolUse.toolUseId` + `toolUse.name` — tool-call identity. Tool calls in streaming go to `/dev/null` because downstream code can't match delta fragments to a call ID. |
| `ContentBlockDelta` | ✅ (Text + ReasoningContent only) | ToolUse delta (input JSON chunks), Citations delta, Image delta, all dropped silently. |
| `ContentBlockStop` | ❌ | Per-block completion signal. We concatenate text + reasoning with no separation boundary. |
| `MessageStart` | ❌ | Role verification. We assume assistant without checking. |
| `MessageStop` | ✅ | stopReason captured. |
| `Metadata` | ✅ (usage only) | `metrics.latencyMs` (new in 1.6.x) dropped — we lose per-call latency attribution. |
| `Trace` | ❌ | Guardrail trace events dropped when `trace = Enabled`. |
| `Citation` (delta) | ❌ | Citation source attribution dropped. |

The response-side `ContentBlock` dispatch at `BedrockMultimodalPipe.kt:261-365` is even narrower — only `Text`, `Image`, and `Document` are handled; `ToolUse`, `ToolResult`, `ReasoningContent`, `GuardContent`, `CachePoint`, `CitationsContent`, `SearchResult`, `Video`, `Audio` all fall through to `else -> trace(unknownContentBlockType)` at line 357. **Citations, tool calls, and guardrail assessments are silently dropped on every response we receive from a model that emits them.**

**Symptom**: a new SDK version adds `CitationsContentBlock`, the SDK ships it on every response, but `MultimodalContent.citations` is null forever. No trace event reveals the failure mode (the existing `unknownContentBlockType` trace only logs the class name; downstream code never sees the block).

**Verification recipe** before relying on any new provider feature:

```bash
# For Bedrock ConverseStream: enumerate every event we currently dispatch
grep -nE 'as[A-Z][a-zA-Z]+OrNull' TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
# Expected hits: 4-7. Anything < 8 = we're dropping events.

# For Bedrock response ContentBlock dispatch:
grep -nE 'is ContentBlock\\.[A-Z]' TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockMultimodalPipe.kt
# Expected hits: 3 (Text, Image, Document). Anything > 3 = we have uncovered variants.

# Cross-check against the SDK's sealed-class members:
# bedrockruntime-1.8.15.jar's model package has 12 ContentBlock variants.
# 12 - 3 = 9 silently dropped.
```

**Fix shape (when fixing)**: each missing event handler is an additive `else if (event.asXxxOrNull() != null)` branch that captures the relevant fields into a `MultimodalContent` extension field. The schema extension is backward-compatible (downstream consumers must handle the new field as null/empty by default). TDD recipe: pin the missing event with a synthetic `ConverseStreamResponse` fixture, assert the field lands on `MultimodalContent.metadata` (or a new typed field).

**Generalization — apply to every provider**: the same pattern recurs for OpenAI / GenericOpenAI streaming (delta types we ignore), Ollama (think-tag handling), OpenRouter (provider-specific delta types). Each provider's `executeStream` should be audited against its SDK's full event surface before declaring "support for feature X."

### Streaming fragments of typed objects need reassembly, not stringification

The pitfall above gets the SDK to *emit* the events to our code. The next layer down: when multiple events represent fragments of one logical entity, our code must **reassemble them into the typed value** instead of stringifying them into a trace map. The canonical case on Bedrock: the Task 8 first-pass wire captured `CitationsDelta` events into `usageMetadata["citations"]` as `"title=...;source=...;text=..."` strings — visible in traces, invisible on `BedrockCallMetadata.citations: List<Citation>`. The companion fix is `references/2026-07-28-bedrock-sdk-1.6.107-citation-reassembly.md`: per-block accumulator, last-non-null wins on metadata, sourceContent.text fragments concatenate, one typed `Citation` emitted per block at `ContentBlockStop`.

**When fixing** any future "the model returned fragments of X" task (citations, images, audio, reasoning text, etc.):

1. Verify the SDK shape of the delta event (`javap -public` on the `*Delta` class — it usually has 1-3 optional fields plus `text: String?` or similar).
2. Verify the typed `X` data class the SDK gives the non-streaming path (this is what you reassemble into).
3. Pin per-block accumulator state. Use `perBlockXxx.remove(blockIndex)?.let { ... }` (not `get`) at the stop event so the entry is cleared and absent the returned accumulator.
4. Wire the typed `List<X>` into the `BedrockCallMetadata`-shaped field at the end (`citations = collectedCitations`).
5. Write at least one unit test with a hand-crafted event sequence (single fragment, multi-fragment same metadata, multi-fragment different metadata) + at least one no-NPE defensive test for the non-streaming `CitationsContentBlock { /* no `citations` field */ }` shape.

**The cross-cutting warning** this signals: any feature that produces typed output on the non-streaming path AND fragmented output on the streaming path MUST be wired both ways — see the citation-reassembly reference for the full recipe. Common candidates: Citations (covered), Image bytes (per-block image chunks in some provider streams), Audio chunks (same), Guardrail assessments (one or more per-call), Reasoning content (already covered as `ReasoningContent` delta in Task 7 but only surfaces in `usageMetadata` — should also land on `BedrockCallMetadata.reasoning` as typed content if you ever want downstream consumers).

### `toStreamRequest()` drops guardrail policy fields on the streaming path

At `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:2628`, the `ConverseRequest.toStreamRequest()` extension forwards `guardrailIdentifier` + `guardrailVersion` + `trace` into `ConverseStreamRequest.guardrailConfig`, but drops every policy field from the original `GuardrailConfiguration`:

```kotlin
// toStreamRequest at BedrockPipe.kt:2641-2647
original.guardrailConfig?.let { config ->
    guardrailConfig = GuardrailStreamConfiguration {
        guardrailIdentifier = config.guardrailIdentifier
        guardrailVersion = config.guardrailVersion
        trace = config.trace
        // MISSING: disallowedContentFiltering, contentFilters,
        // sensitiveInformationPolicyConfig, topicPolicyConfig,
        // wordPolicyConfig, contextualGroundingPolicyConfig,
        // automatedReasoningPolicyConfig
    }
}
```

This means a model call configured with inline guardrail policies (topic filters, word filters, sensitive-info filters, contextual grounding, automated reasoning) **silently loses all policy enforcement on the streaming path**. Bedrock treats the streaming request as trace-only. The non-streaming `ConverseRequest` carries the policies correctly; the `ConverseStreamRequest` does not. Same call site, two divergent behaviors.

This is a sibling case to the documented-contract-without-enforcement pattern (see `tpipe-pipe-internals` "Path-name map keys and lookup keys must agree"): the streaming SDK type expects the same policy fields as the non-streaming type, but the mapping extension doesn't propagate them. The contract is silent about the mapping, so the bug is silent too.

**Symptom**: streaming calls configured with topic/word/sensitive-info/contextual-grounding/automated-reasoning guardrail policies pass through with no policy enforcement. Logs may show guardrail invocation but assessments are empty. No trace event surfaces the missing fields. The non-streaming equivalent call (same model, same prompt, same guardrail config) enforces the policies correctly — divergence is the diagnostic signal.

**Verification recipe**:

```bash
# Read toStreamRequest and confirm every policy field on GuardrailConfiguration
# has a corresponding assignment to GuardrailStreamConfiguration.
grep -nE 'guardrailConfig|GuardrailStreamConfiguration|GuardrailConfiguration' \
    TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
# The mapping site must forward: guardrailIdentifier, guardrailVersion, trace,
# AND all of: disallowedContentFiltering, contentFilters,
# sensitiveInformationPolicyConfig, topicPolicyConfig, wordPolicyConfig,
# contextualGroundingPolicyConfig, automatedReasoningPolicyConfig.
```

**Fix shape**: extend the mapping block to forward every field present on `GuardrailConfiguration` to its `GuardrailStreamConfiguration` sibling. Same field names, same types. ~10-line patch per missing field cluster.

### OpenAI-compatible providers can deviate from the canonical OpenAI event-name wire format

When a provider claims "OpenAI-compatible" (Bedrock Mantle, OpenRouter, vLLM with OpenAI shim, any third-party provider that re-skins OpenAI's chat-completions / responses endpoints), the wire event names that arrive on the SSE stream may differ from OpenAI proper. The most common deviation is shortening event-type discriminators — Mantle's `/v1/responses` SSE stream emits `response.reasoning.delta` and `response.reasoning.done` instead of OpenAI proper's `response.reasoning_text.delta` / `…_done`. Our `OpenAIResponsesSseParser.parseLine` dispatch table only knew the long-form names, so the Mantle reasoning deltas fell into the `else -> Unknown(raw)` branch and were silently dropped. The internal accumulator (`reasoningBuilder.append(delta)`) never received a single Mantle reasoning fragment, so `streamingReasoning` stayed empty, so `MultimodalContent.modelReasoning` was empty on the returned content even though Mantle delivered reasoning correctly on the wire.

The shape of the bug is the same family as the streaming-event-drop and `toStreamRequest()` drop patterns already in this skill: a documented contract (the parser dispatch) is silent about a sibling (a provider that emits a related but non-canonical event name), so the bug is silent too.

**Symptom**: a provider that claims OpenAI-compatible returns reasoning / citation / tool fragments on the wire, but `MultimodalContent.modelReasoning` (or analogous surface) is empty on every call. The trace dump will show the events arriving as `Unknown` raw strings (no reasoning metadata, no accumulator activity). The internal accumulator's `append(...)` call never fires.

**Verification recipe** before shipping any "OpenAI-compatible provider" wiring:

```bash
# Capture the raw SSE wire from the provider with a tiny Python SigV4/curl probe
# and enumerate every event: line. Compare against the parser's dispatch table.
python3 -c "..."  # or curl --no-buffer -N ...

# Then check what the parser currently knows:
grep -nE '\"response\\.' TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/api/OpenAIResponsesSseParser.kt
# Compare the two lists. Any event: line the parser doesn't recognize is dropped to Unknown.
```

**Fix shape** (when fixing): add the provider's event-name variant to the parser dispatch table. The handler function is already correct (it parses the same JSON shape); only the dispatch key needs the new name. Example from the Mantle Round 3 fix:

```kotlin
"response.reasoning_text.delta" -> parseReasoningTextDelta(dataJson, raw)
"response.reasoning_text.done"  -> parseReasoningTextDone(dataJson, raw)
// MANTLE SHORT-FORM (no _text infix):
"response.reasoning.delta"      -> parseReasoningTextDelta(dataJson, raw)
"response.reasoning.done"       -> parseReasoningTextDone(dataJson, raw)
```

Companion fix (often needed in parallel): the pipe's streaming entry point may also need to widen its return type from `String` to `MultimodalContent` so the captured `streamingReasoningText` actually reaches `MultimodalContent.modelReasoning` on the returned object. The Round 3 fix for Mantle did both: parser dispatch widening + `executeStreaming(...)` and `executeStreamingDirect(...)` return-type widening (with caller `.text` unwraps). See `references/2026-07-29-bedrock-mantle-streaming-reasoning-round3.md` for the full worked example.

**Generalization — apply this check to every "OpenAI-compatible" provider**: the SSE event-name vocabulary is not standardized by any public spec; each provider is free to shorten, lengthen, or rename. The Mantle deviation is the first one we hit but won't be the last. The parser must accept the canonical OpenAI names AND a per-provider alias list; new providers = new dispatch entries, not new parser files.

### Bedrock Mantle is NOT a Bedrock SDK feature — route through `GenericOpenAIPipe`

Bedrock Mantle (`bedrock-mantle.{region}.amazonaws.com/openai/v1/...`) is the OpenAI-compatible chat-completions / responses endpoint AWS added to Bedrock. It is a SEPARATE protocol surface; it is NOT generated by the `bedrockruntime` Smithy model, and no `aws.sdk.kotlin:bedrockmantle` artifact exists on Maven Central. Adding it does not require a Bedrock SDK upgrade — it requires routing through `TPipe-GenericOpenAIPipe` with the `baseUrl` swapped and the auth header switched from OpenAI Bearer to Bedrock API key (`bedrock-api-key`).

| Layer | Bedrock Converse/Invoke | Bedrock Mantle |
|---|---|---|
| SDK | `aws.sdk.kotlin:bedrockruntime:1.6.107+` | None — use OpenAI SDK or raw HTTP via Ktor |
| Pipe | `BedrockPipe` (the entire proprietary-builder apparatus) | `GenericOpenAIPipe` with Mantle endpoint |
| Auth | `StaticCredentialsProvider(AWS creds)` or default chain | `bedrock-api-key` header (separate IAM concern) |
| Model ID namespace | `anthropic.claude-sonnet-4-...`, `amazon.nova-pro-v1:0`, etc. | `bedrock-mantle/<vendor>.<model>` (OpenAI-prefix style) |
| Request shape | `ConverseRequest` / `InvokeModelRequest` | OpenAI `ChatCompletionRequest` |
| Structured output | Bedrock-native `outputConfig.jsonSchema` (added in 1.6.x) | OpenAI `response_format.json_schema` (via `GenericOpenAIPipe.setResponseFormat`) |
| Streaming events | `ConverseStreamResponse` sealed class (Bedrock-specific) | OpenAI `ChatCompletionChunk` SSE events |

**Symptom of misuse**: a future session adding Mantle support by editing `BedrockPipe.kt` will hit a wall — there is no Mantle-aware class in the bedrock SDK to import. The right shape is a `MantlePipe` factory in `TPipe-GenericOpenAIPipe` that wraps the existing OpenAI pipe with Mantle-specific config (URL, auth header, model-prefix parsing).

**Verification recipe** before any "add Mantle support" request:

```bash
# Confirm no Mantle artifact exists in the SDK family
curl -sI 'https://repo1.maven.org/maven2/aws/sdk/kotlin/bedrockmantle/' | head -1
# Expected: 404 Not Found

# Confirm GenericOpenAIPipe has the surface to take a custom baseUrl
grep -nE 'setBaseUrl|baseUrl' TPipe-GenericOpenAIPipe/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt
```

### `setJsonOutput()` prompt-injection vs SDK-native `outputConfig.jsonSchema` are incompatible when both are active

TPipe's structured-output path is prompt-injection: `setJsonOutput(schema)` flips `supportsNativeJson = false` (`Pipe.kt:2780-2810`), and the schema is appended to the system prompt as English instructions. The model is TOLD to return JSON; nothing in the wire protocol enforces it.

The provider SDK's native structured output (Bedrock `ConverseRequest.outputConfig.jsonSchema`, OpenAI `response_format.json_schema`, Anthropic `output_format`) is WIRE-LEVEL enforcement: the service refuses to emit text outside the schema. The model is CONSTRAINED, not instructed.

Wiring BOTH at once on Bedrock causes three problems:

1. **Double-prompting**: the schema gets serialized into the system prompt verbatim by `Pipe.kt:2028-2150`, AND the service receives it again as a wire constraint. Token waste on the input side, latency waste on the model side.
2. **PCP-merged-mode break**: when `hasPcpTools && hasJsonOutput`, `Pipe.kt:2034-2073` instructs the model to return tool calls as JSON in the text output (`return an array of the following json: [${pcpRequestExample}]`). If `outputConfig.jsonSchema` is wired, the service locks the text to the user-defined schema, and tool calls expressed as JSON-in-text are syntactically invalid against that schema. The model has to choose: native `ContentBlock.ToolUse` blocks (the right way), or break the schema contract.
3. **Downstream parser dies**: `Pipe.kt:4893` parses the schema string (not the response) to populate pipeline templates. The response-parser path is `MultimodalContent.text` → consumer. With native `outputConfig`, the text is guaranteed JSON matching the schema — easier to parse, but every existing consumer that handled prose-or-JSON now sees JSON-only.

**Symptom of misuse**: a future session wires `outputConfig = OutputConfiguration { textFormat = TextFormat { jsonSchema = ... } }` into every `build*ConverseRequest` AND keeps the prompt-injection path active. Token costs double, tool-call reliability degrades, and the merged-mode users (those with both `setJsonOutput` and `pcpContext.tpipeOptions`) silently lose tool-call functionality.

**Mitigation shape (when wiring native)**: gate behind a feature flag — e.g. `setNativeStructuredOutput(enabled: Boolean = true)`:

```kotlin
fun setNativeStructuredOutput(enabled: Boolean = true): BedrockPipe {
    this.useNativeStructuredOutput = enabled
    if (enabled) {
        this.supportsNativeJson = true   // skip prompt injection
        this.useMergedModeForTools = false // force native setTools() path
    }
    return this
}
```

Then in every `build*ConverseRequest`, conditionally set:

```kotlin
if (useNativeStructuredOutput && jsonOutput.isNotEmpty()) {
    outputConfig = OutputConfiguration {
        textFormat = TextFormat {
            jsonSchema = JsonSchemaDefinition {
                name = "TPipeOutput"
                schema = Document.Map(jsonObjectToMap(...))
            }
        }
    }
}
```

This is a BREAKING change for users who currently combine `setJsonOutput` + `pcpContext.tpipeOptions`. They must migrate to native `outputConfig` + native `setTools()`. Worth a release-note callout.

**Verification recipe** before any native structured-output work:

```bash
# Confirm prompt-injection is currently the path for BedrockPipe
grep -nE 'supportsNativeJson|outputConfig|outputFormat' \
    TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
# Expected: zero hits for outputConfig/outputFormat on BedrockPipe side.
# Hit count of 0 = prompt-injection is the only path; native structured
# output is unimplemented.

# Confirm the Pipe base flips supportsNativeJson on setJsonOutput
grep -nE 'ensureJsonPromptInjectionEnabled|supportsNativeJson' \
    TPipe/src/main/kotlin/Pipe/Pipe.kt
# Expected: every setJsonOutput overload calls ensureJsonPromptInjectionEnabled.
```

**Generalization**: the same conflict shape applies to OpenAI (`response_format.json_schema` vs prompt injection), Anthropic (`output_format` vs prompt injection), Ollama (`format` field vs prompt injection). Each provider's native structured output must be gated behind a feature flag to coexist with TPipe's prompt-injection path during migration.

### OpenRouter-style `abort() = null` is the previously-fixed GenericOpenAI bug, repackaged

When a provider pipe's `abort()` method does `httpClient?.close(); httpClient = null` (or any equivalent "close and dereference" pattern), the next call after abort throws `IllegalStateException("Pipe not initialized. Call init() first.")` — even though `init()` was already called. The pipe is alive; only the client handle is dead. This is the exact shape of the GenericOpenAI bug that was previously fixed (`GenericOpenAIPipe.abort()` at line 826-842): closing and reusing the same Ktor CIO handle triggers `IOException: connection closed` on the next request, so the fix was to close AND recreate the handle.

The 2026-08-02 audit found this same bug alive in `OpenRouterPipe.abort()` (`OpenRouterPipe.kt:575-584`):

```kotlin
override suspend fun abort() {
    trace(TraceEventType.PIPE_FAILURE, TracePhase.EXECUTION, …)
    httpClient?.close()
    httpClient = null            // ← the bug
    super.abort()
}
```

**Symptom**: any consumer code that aborts the pipe and then re-uses it (e.g. retry-swap orchestrators, failure-recovery flows, test harnesses that share pipe instances) hits `IllegalStateException` on the second call. The first call after `init()` works. The abort path silently bricks the pipe.

**Verification recipe**:

```bash
# Find every provider's abort() method and check the post-close assignment
search_files 'override suspend fun abort' --target content --path TPipe-*/src/main/kotlin
# Then read each abort() and confirm the post-close assignment is NOT `= null`.
# If it's `= null`, the bug is live.
```

**Fix shape**: mirror the GenericOpenAI fix. Close the existing client AND create a fresh one in the same `abort()` body:

```kotlin
override suspend fun abort() {
    trace(TraceEventType.PIPE_FAILURE, TracePhase.EXECUTION, …)
    if (ownsHttpClient) {
        httpClient?.close()
        httpClient = createHttpClient()    // fresh handle, not null
    }
    super.abort()
}
```

The `ownsHttpClient` guard is essential for test-only clients injected via `injectHttpClientForTest(...)` — those must not be closed by the pipe, only by the test caller.

### Stop-reason capture is independent of error mapping — both must be checked in a parity audit

A provider can have perfect tracing (every boundary emits `trace(API_CALL_*)`) AND perfect `P2PException` wrapping (every `HttpRequestTimeoutException / SocketTimeoutException / ConnectException` maps to the right P2P error code) AND STILL never capture a `finish_reason` / `stop_reason` from the wire. These are independent axes and the audit must check each one.

The 2026-08-02 audit found this exact shape in OpenRouter: 8 trace sites, 3 P2PException mappings at the outer catch sites, but **zero reads of `choices[0].finish_reason` anywhere in the streaming path**. A `length`-truncated response was indistinguishable from a `stop`-terminated response. Truncation detection relied entirely on response length heuristics, not on the wire signal.

**Symptom**: a model that hit its token cap on a long context returned a truncated answer with no signal to the caller. The trace dump showed `API_CALL_SUCCESS` with a `responseLength` metadata field, but no `stopReason`. Operators relying on `metadata["stopReason"] == "length"` to trigger truncation handling got silent truncation.

**Verification recipe**:

```bash
# Find every provider's wire-event read sites
search_files 'finish_reason|finishReason|stop_reason|stopReason' \
  --target content --path TPipe-*/src/main/kotlin
# 0 hits in a provider = stop-reason capture is missing regardless of how good
# the tracing and error mapping are.
```

**Fix shape**: add a single read in the streaming chunk parser. For OpenAI Chat Completions:

```kotlin
// In SseParser.parseChunk or the streaming handler
val finishReasonEl = choiceObj?.get("finish_reason")
val finishReason = (finishReasonEl as? JsonPrimitive)?.contentOrNull
if (finishReason != null && streamingFinishReason == null) {
    streamingFinishReason = finishReason
    metadata["stopReason"] = finishReason
}
```

This is a 5-line fix per provider, isolated to the streaming parse layer. The `metadata["stopReason"]` write is what makes the audit dimension flip from ❌ to ✅.

### MCP is a bridge, not a provider — exclude it from cross-provider parity scorecards

`TPipe-MCP` converts MCP manifests to PCP options and hosts the stdio/HTTP server. It does NOT call any LLM API and does NOT have a `trace()` boundary to emit events on. A parity scorecard that includes MCP will mark it as ❌ across all four dimensions — which is correct (MCP has no LLM call to trace, no stop reason to capture, no socket to drop, no error to wrap). The scorecard will look like MCP is "the worst provider" when it's actually not a provider at all.

**Symptom**: an operator looking at a parity scorecard that includes MCP will see a red row at the bottom and ask "fix MCP" — which is the wrong response. The right response is "MCP is a bridge, exclude it from the scorecard, or score it on a separate dimension set (tool-call routing, JSON-RPC error code fidelity, manifest conversion correctness)."

**Verification recipe**:

```bash
# Confirm MCP has zero trace sites (this is correct behavior)
search_files 'trace\(' --target content --path TPipe-MCP/src/main/kotlin
# Expected: 0 hits
```

**Fix shape (when the operator wants MCP in the scorecard anyway)**: define a separate dimension set for bridge modules:
- Tool-call routing correctness (does `call_tool(name, args)` dispatch to the right registered tool?)
- JSON-RPC error-code fidelity (does the bridge return `-32601 Method not found` for unknown methods, not a generic `Internal error`?)
- Manifest conversion correctness (does `McpToPcpConverter.convert(...)` produce a `PcpContext` that survives `PcpExecutionDispatcher.executeRequest(...)` round-trip?)

These are different from provider-level dimensions. Forcing MCP into the LLM-provider scorecard produces a misleading red row.

### A contract with a config site AND a builder site also needs a consumer-site count

When a class-level feature is declared on a `XxxConfig` data class AND exposed via a DSL builder method (`XxxBuilder.featureName(...)`), the contract looks complete. But the contract is silent about which classes must CONSUME the field. The number of consumers IS the parity scorecard, and the gap between (config + builder) sites and consumer sites is the audit finding.

The 2026-08-08 audit found this exact shape for `TraceConfig.autoExport`:

- Configuration site: `Debug/TraceConfig.kt:19` (field declaration)
- Builder sites: `Debug/TracingBuilder.kt:27`, `Pipeline/PumpStationDsl.kt:2117` (DSL methods)
- Consumer sites: only `Pipeline.kt:865` + `PumpStation.kt:2824` — 2 of 6 containers

The user wires `manifold { tracing { autoExport(true) } }` and gets nothing because the contract is silently ignored by 4 of 6 containers. The DSL accepted the call, the configuration site stored the value, but the consumer side never reads it.

**Symptom**: a feature appears to work (the call site is satisfied, no compile error, no runtime exception), but the side effect never happens. No trace event reveals the missing consumer. Operators can't tell whether autoExport is silently ignored vs. silently failing until they look at the destination directory.

**Verification recipe** before declaring "feature X is wired":

```bash
# Step 1: locate the field declaration
grep -nE 'val featureName' /path/to/Config.kt

# Step 2: locate the builder method
grep -rnE 'fun featureName\b' /path/to/Dsl.kt

# Step 3: locate EVERY consumer of the field across the codebase
search_files 'featureName' --target content --path src/main/kotlin
# The count of consumer sites must equal the count of implementations that should honor it.
# For TraceConfig features: 6 containers (Pipeline, PumpStation, Manifold, Splitter, Junction, DistributionGrid).
# If consumer count < N, the gap is the audit finding.
```

**Fix shape**: replicate the consumer block across the missing implementations, identical shape with implementation-specific id-taker length and filename prefix. ~10 lines per missing consumer.

### Empty-body interface defaults silently no-op when implementers forget to override

Kotlin interface methods with empty `{}` bodies compile fine and look "implemented" to the type system. But a concrete class that forgets to override silently inherits the no-op default — no compile error, no runtime exception, no trace event. The contract looks satisfied from outside; the behavior is missing.

The 2026-08-08 audit found 11 such methods in `P2P/P2PInterface.kt` (L30, 36, 42, 57, 76, 96, 109, 137, 158, 164, 179):

```kotlin
// All eleven follow the same shape — empty body, no exception:
fun setP2pDescription(description: P2PDescriptor) {}
fun setP2pTransport(transport: P2PTransport) {}
fun setP2pRequirements(requirements: P2PRequirements) {}
fun setContainerObject(container: Any) {}
fun setTokenBudgetRecursive(budget: TokenBudgetSettings) {}
fun setPipeSettingsRecursively(settings: TPipeSettings) {}
fun setStreamingCallbackRecursive(callback: StreamingCallback) {}
fun enableStallDetectorRecursive(callback: StallCallback, config: StallConfig) {}
fun setConverseRoleRecursive(role: ConverseRole) {}
fun setParentInterface(parent: P2PInterface) {}
fun executeP2PRequest(request: P2PRequest): P2PResponse { /* empty */ }
```

**Symptom**: a container that needs `setTokenBudgetRecursive(...)` to propagate budgets to its sub-pipes finds the budget missing on the sub-pipes. The container calls `setTokenBudgetRecursive(...)`; the concrete P2PInterface (e.g. a custom user-supplied agent) inherits the no-op default; the budget is silently lost. No log line, no trace, no exception. The downstream pipe runs on default budget.

**Verification recipe**:

```bash
# Step 1: list every fun declaration in the interface with empty body
grep -nE '^\s*fun\s+\w+.*\{\s*\}' /path/to/Interface.kt
# Expected in well-designed interfaces: 0 hits. Every interface method either has a real body
# or is `abstract` (which forces overrides at compile time).

# Step 2: cross-check that every concrete subclass overrides all of them
# (The fix is to make the interface methods `abstract`, which forces override at compile time.)
```

**Fix shape**: convert empty-body interface methods to `abstract` (no body). The compiler then forces every concrete subclass to provide a real implementation — a forgot-to-override becomes a compile error, not a silent no-op. This is the inverse of "make the default `{}` to be a courtesy default" — the courtesy default is a death-by-protocol pattern that surfaces only at runtime.

The cross-cutting warning: any interface that mixes `abstract` methods with `{}` defaults is a future-silent-failure surface. Audit every P2PInterface-style interface for this pattern.

## Wiring a new SDK Converse field (the SOURCE side)

The audit methodology above is the SINK side: "does this feature actually reach the wire?" The complement is the SOURCE side: when a NEW Converse field lands in aws-sdk-kotlin (e.g. `performanceConfig`, `requestMetadata`, `promptVariables`, `outputConfig`), how do you wire it end-to-end through TPipe's 14 `build*ConverseRequest` builders and the `BedrockMultimodalPipe` delegate pattern?

The Task 3 wire of `performanceConfig` on the `bedrock-sdk-1.6.107-upgrade` branch is the canonical worked example. The pattern is a five-site change that ships a new optional Converse field from a user-facing setter on `BedrockPipe` to the wire:

### Site 1 — the user-facing setter on `BedrockPipe`

Mirror the existing `serviceTier` / `guardrailIdentifier` setters. Private field, fluent setter returning `this` for chaining, getter, clear method. Mark transient (not serialized into `TPipeSettings`).

```kotlin
@kotlinx.serialization.Transient
private var performanceConfig: PerformanceConfiguration? = null

fun setPerformanceConfig(latency: PerformanceConfigLatency): BedrockPipe {
    this.performanceConfig = PerformanceConfiguration { this.latency = latency }
    return this
}
fun getPerformanceConfig(): PerformanceConfiguration? = performanceConfig
fun clearPerformanceConfig(): BedrockPipe { this.performanceConfig = null; return this }
```

### Site 2 — the `apply*()` extension on `ConverseRequest.Builder`

The shape of the wire call. Declared as a private extension (or protected if `BedrockMultimodalPipe` needs to call it) right next to the existing `applyGuardrailConfig()` extension. One-liner, idempotent (no-op when the field is null):

```kotlin
private fun ConverseRequest.Builder.applyPerformanceConfig() {
    this@BedrockPipe.performanceConfig?.let { this.performanceConfig = it }
}
```

### Site 3 — every `build*ConverseRequest` callsite (14 builders + the ContentBlock overloads)

The 14 builders all share the same tail pattern. After `serviceTier = ServiceTier { type = mapServiceTier() }` and before `applyGuardrailConfig()`, insert the new `apply*()` call. The position is load-bearing: service tier is the canonical "what tier" line, guardrail is the canonical "what safety" line, and a new cross-cutting field sits between them.

**Verification**:
```bash
grep -nE 'applyPerformanceConfig' TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
# Expected: 1 declaration + 14 callsites (one per build*ConverseRequest method).
# A count of < 15 means a builder was missed.
```

If the project compiles with `-Werror`, a missed callsite surfaces as `Unused private extension function 'applyPerformanceConfig'`. Do NOT suppress — add the callsite to the missing builder.

The 14 builders (verified on `bedrock-sdk-1.6.107-upgrade` HEAD): GptOss, Glm, DeepSeek, Kimi, MiniMax, Nova, Claude, Titan, Cohere, Llama, Mistral, AI21, Qwen, Generic. The ContentBlock-based overloads inherit from the prompt-based ones via direct delegation (e.g. `buildGlmConverseRequest(contentBlocks) = buildGlmConverseRequest(prompt)`, not a separate builder block), so a single callsite covers both paths.

### Site 4 — `BedrockMultimodalPipe` delegate path

`BedrockMultimodalPipe` does NOT build `ConverseRequest` directly. It uses a `when { ... build*ConverseRequest(contentBlocks) ... }` dispatcher at `BedrockMultimodalPipe.kt:221-236` that calls the parent-class builders. The wire is inherited automatically — no separate extension callsite needed.

For verification gates that demand an explicit `applyX()` callsite in the multimodal pipe (e.g. `grep -nE 'applyPerformanceConfig' BedrockMultimodalPipe.kt | count >= 1`), add a `protected` helper on `BedrockPipe` that takes a finished `ConverseRequest` and returns a copy with the field applied:

```kotlin
protected fun applyPerformanceConfig(converseRequest: ConverseRequest): ConverseRequest {
    val cfg = performanceConfig ?: return converseRequest
    return converseRequest.copy { performanceConfig = cfg }   // see gotcha #1 below
}
```

Then in `BedrockMultimodalPipe.kt`:

```kotlin
val converseRequest = applyPerformanceConfig(when {
    modelId.contains("qwen") -> buildQwenConverseRequest(contentBlocks)
    // ... 13 other branches ...
    else -> buildGenericConverseRequest(contentBlocks)
})
```

The helper is idempotent (no-op when the field is null) and `protected` so the multimodal subclass can call it. The inherited builders' `applyPerformanceConfig()` already folded the field in, so the copy is a no-op write — the call exists to satisfy the verification gate and to document that the multimodal pipe is wired.

### Site 5 — `toStreamRequest()` passthrough

The `ConverseRequest.toStreamRequest()` extension at `BedrockPipe.kt:2628` is a manual field-by-field mapper. **Verify** the new field is present in the forward list. The mapping site already includes `performanceConfig`, `promptVariables`, `requestMetadata` for the 1.6.107 fields. For older SDK versions, the field may be missing — add it. Symmetry rule: every field on `ConverseRequest` that exists in the SDK version you're targeting should be in the `toStreamRequest` forward list.

**Verification**:
```bash
sed -n '2628,2680p' TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
# Compare against the SDK's ConverseRequest fields:
# grep the SDK jar for `public final` fields on ConverseRequest and verify each is forwarded.
```

### Five gotchas hit during the wire

1. **`ConverseRequest.copy(...)` takes a builder lambda, not named parameters.** The SDK generates `copy(kotlin.jvm.functions.Function1<Builder, Unit>)`, NOT the named-parameter form a data class would normally have. Writing `copy(performanceConfig = cfg)` compiles to `e: No parameter with name 'performanceConfig' found`. Correct form: `copy { performanceConfig = cfg }`. Verify by checking the SDK jar:
   ```bash
   unzip -p ~/.gradle/caches/modules-2/files-2.1/aws.sdk.kotlin/bedrockruntime-jvm/1.6.107/*/bedrockruntime-jvm-1.6.107.jar \
     aws/sdk/kotlin/services/bedrockruntime/model/ConverseRequest.class | javap -p /dev/stdin
   # Expected signature: copy(kotlin.jvm.functions.Function1<...Builder, kotlin.Unit>)
   ```

2. **A private extension can't be called from a subclass.** `BedrockMultimodalPipe extends BedrockPipe`, so a `private fun ConverseRequest.Builder.applyX()` declared in `BedrockPipe` is invisible to `BedrockMultimodalPipe`. Promote to `protected` if the multimodal path needs to call it directly. The 14-builder callsites still work — they share the file with the declaration.

3. **The wrapper-vs-enum distinction in tests.** `getPerformanceConfig()` returns `PerformanceConfiguration?` (the wrapper), not `PerformanceConfigLatency` (the enum). A test like `assertEquals(PerformanceConfigLatency.Optimized, pipe.getPerformanceConfig())` fails with `expected: <Optimized> but was: <PerformanceConfiguration(latency=Optimized)>`. Fix: assert on `.latency`:
   ```kotlin
   assertEquals(PerformanceConfigLatency.Optimized, pipe.getPerformanceConfig()?.latency)
   ```

4. **The `@Suppress` prohibition is real and load-bearing.** When the project compiles with `-Werror` and a private extension is declared but unused, the build fails. The temptation is `@Suppress("unused") private fun ...`. Do NOT do this — the warning is the only signal that a builder was missed. Add the callsite to the missing builder, suppress nothing.

5. **`toStreamRequest()` field drops are a separate bug class from missing builder callsites.** A builder that calls `applyPerformanceConfig()` correctly populates the field on `ConverseRequest`, but if `toStreamRequest()` doesn't forward `performanceConfig`, the streaming path loses the field. Symmetric verification: every field set inside `applyX()` must be present in the `toStreamRequest` forward list. The audit recipe in `tpipe-pipe-feature-audit/SKILL.md` "Provider-SDK response events are silently dropped" is the response-side cousin; this is the request-side equivalent.

## Verification recipe

After auditing, for every pipe classified as ELIGIBLE for the feature, verify the actual state by running:

```bash
# For tier on Bedrock, check whether any active setServiceTier call exists for the model
grep -rn "setServiceTier(BedrockPriorityTier\." path/to/codebase
```

A grep that returns only `// setServiceTier(...)` comments (and zero active calls) is the canonical "feature available, documented, drafted, but never active" signal. This is the state Autogenesis's qwen235B agents were in before this audit.

For OpenRouter tier (where the config dataclass DOES carry the field), the verification is the opposite — every call site that constructs an `OpenRouterConfiguration` is checked for `serviceTier` set:

```bash
grep -rn "OpenRouterConfiguration(" path/to/codebase -A 30
```

A grep that returns constructors without `serviceTier = ...` is the equivalent "feature is opt-in via the config surface but never opted into" signal.

## Worked case study

The Autogenesis qwen235B Flex-tier eligibility audit (2026-07-25) is the canonical worked example. Full transcript, every qwen235B use across 18 files, the JSON output class for each, and the ELIGIBLE / NARRATIVE / REASONING / RETRY-SWAP verdict for each: see `references/2026-07-25-autogenesis-flex-tier-eligibility.md`.

The headline numbers from that audit:

- 23 unique line-level qwen235B references
- 34 judged units across them
- 13 ELIGIBLE main pipes
- 17 NARRATIVE main pipes (ineligible — feature is wrong tool)
- 4 REASONING / RETRY-SWAP sites (governed by separate mechanisms)
- Zero active `setServiceTier(...)` calls on qwen235B main pipes at the time of audit

The summary pattern: the feature was available, wired into the builder, draft-setted on every main pipe, commented out at the moment of merge, and the reasoning-pipe-side companion (`useFlex`) was either unset or default false. Every layer was inert by the time the request reached the wire.

## Cross-references

- `tpipe-pipe-internals` — the parent class-level skill for Pipe internals. This audit skill extends it on the "does the feature actually fire?" verification side.
- `tpipe-context-pull-builder-repair` — the fix-side companion for silent no-ops on context-pull builders. Different mechanism (the pull-builder bug is "setter exists, branch missing"), same class-level signal ("documented behavior does not actually fire").
- `tpipe-reasoning-pipes` — reasoning-pipe mechanics, especially the `setReasoningPipe` boundary where features silently fail to propagate.
- `references/2026-07-25-autogenesis-flex-tier-eligibility.md` — Flex-tier eligibility audit on Autogenesis's qwen235B agents (23 line-level uses, 13 ELIGIBLE / 17 NARRATIVE / 4 REASONING/RETRY-SWAP, zero active setServiceTier calls).
- `references/2026-07-27-bedrock-sdk-upgrade-consequences.md` — Bedrock SDK upgrade audit findings: streaming event coverage gaps, response-side `ContentBlock` drop-on-floor, `toStreamRequest()` guardrail field-drop, Mantle routing rule, structured-output conflict shape. Load before any `aws.sdk.kotlin:bedrockruntime` version bump, or when investigating which provider features are silently no-op on BedrockPipe.
- `references/2026-07-28-bedrock-sdk-upgrade-wiring-source-side.md` — worked SOURCE-side wire pattern (Task 3 `performanceConfig`): the 14-builder + 1-multimodal wire + `toStreamRequest()` passthrough + the 5 site-specific gotchas (copy() lambda form, private-vs-protected extension visibility, wrapper-vs-enum, @Suppress prohibition, toStreamRequest field drops).
- `references/2026-07-28-bedrock-sdk-upgrade-sink-side-streaming-event-wire.md` — worked SINK-side fix for event subscription (Task 7 ContentBlockStart/Stop + ToolUse streaming handlers): the 4 new event handlers + the test seam (`executeConverseStreamForTest` + `toConverseRequestForTest`) + the `BedrockCallMetadata` population + 7 gotchas (ConverseStreamOutput vs ConverseStreamResponse, ConversationRole enum, non-nullable contentBlockIndex, abstract Document, BedrockRuntimeClient interface fakes, seam symmetry, internal vs TestableBedrockPipe). Pairs with the citation-reassembly reference below.
- `references/2026-07-28-bedrock-sdk-1.6.107-citation-reassembly.md` — worked SINK-side fix for streaming-fragment reassembly into typed objects: `BedrockCallMetadata.citations: List<Citation>` now populated on both streaming and non-streaming paths. Five-site wire (state + delta handler + finalize + populate + tests) + 5 gotchas (wrong SDK method names, conflated `CitationGeneratedContent`/`CitationSourceContent` type hierarchies, `InvokeGuardrailChecks` vs `ApplyGuardrail` request shapes, visibility of subclass-inherited `bedrockClient`, subagent behavioral correction). The complement of the streaming-event-wire reference: events go IN, fragments come OUT — both surface under "response-side silent-no-op" but at different layers.
- `references/2026-07-29-bedrock-mantle-streaming-reasoning-round3.md` — worked SINK-side fix for "OpenAI-compatible provider deviation" + the canonical Kotlin override-return-type widening pattern (sibling-helper pattern, see `tpipe-pipe-internals` "Kotlin override return-type widening is forbidden"). Captures Mantle Round 3: parser dispatch widening (`response.reasoning.delta` / `.done` added as Mantle aliases alongside the long-form OpenAI proper names) + `executeStreaming(...)` and `executeStreamingDirect(...)` return-type widening from `String` to `MultimodalContent` + caller `.text` unwraps at the two call sites that need `String`-shaped returns. Six session-specific gotchas in the reference, including: the parser fix alone was insufficient (the streaming boundary was also discarding the captured reasoning via `String` returns), the Round 2 `generateTextMultimodal` helper set the precedent for the Round 3 sibling-helper pattern, Ktor streaming goes through `executeStreaming` not `executeStreamingDirect` when env SigV4 is in use (so the Round 3 fix needed to widen BOTH streaming entry points, not just the direct one), and the new-test verification demanded JUnit-XML-authoritative pass counts because gradle stdout drops `PASSED` markers when tests produce heavy stdout.
- `references/2026-07-30-cross-repo-streaming-parity-triage.md` — the cross-repo triage methodology for cross-cutting features that span SDK and consumer repos. Streaming, citations, guardrails, prompt caching all have the same shape: the SDK side has a primitive (`setStreamingCallback` + `emitStreamingChunk` + manager) and a test surface, the consumer side has per-agent wiring that must route to a dispatcher (`AgentWorkStreamDispatcher.appendChunk`). The four-cell gap matrix (prim / wire / test × SDK / consumer) separates work by repo: SDK side verdict = "complete" if all three SDK cells have passing tests that exercise callback delivery; consumer side verdict = "broken" if per-agent wiring is missing. Three pitfalls: (1) live tests that pass `setStreamingEnabled(true)` and assert text content do NOT verify callback delivery — the wire-content path is independent of the callback delivery path; (2) the Bedrock `streamingCallbacks { add(...) }` builder DSL is not portable to Mantle — `GenericOpenAIPipe` has only single-callback, so consumer code must dispatch on pipe type; (3) `setStreamingEnabled(true)` without a callback is a silent no-op — the pipe runs in streaming mode but no listener catches the chunks, and there is no error signal.
- `references/2026-08-02-streaming-stall-detector-audit.md` — the canonical worked example of a streaming-observer feature: pipe-level cross-cutting feature that fires on statistics of the chunk stream, not on the wire signal. Extends the five-path wire-reach recipe to six paths (the streaming callback manager chain) for any feature that observes the chunk stream. Eight pitfalls captured from the 2026-08-02 audit: silent no-op without streaming, conjunctive trigger shape (max not sum), population vs sample variance, first-token early-return, suspend callback via GlobalScope, separate retry counter, lifecycle triple (set/clear-on-abort/clear-in-finally), and pipeline-propagation-is-config-only. Six-check verification recipe at the bottom of the reference.
- `references/2026-08-02-provider-feature-parity-breakdown.md` — the cross-provider feature parity audit worked example: 4 dimensions × 4 LLM providers (Bedrock, GenericOpenAI, Ollama, OpenRouter; MCP excluded as bridge-not-provider). Scorecard surfaces GenericOpenAI as the only fully-connected provider, Bedrock as fully-traced-but-no-P2PException, Ollama as no-error-mapping, OpenRouter as no-finish_reason + abort()-nulls-client. Three class-level pitfalls captured: previously-fixed-bug-resurfaces (OpenRouter `abort() = null`), independent-dimensions (stop-reason vs error-mapping), and bridge-vs-provider (MCP exclusion). Full file:line reference index at the bottom of the reference for every cross-provider fix.
- `references/2026-08-08-trace-config-cross-container-parity.md` — the cross-container parity audit worked example: `TraceConfig.autoExport` honored by 2 of 6 containers (Pipeline, PumpStation), silently ignored by 4 (Manifold, Splitter, Junction, DistributionGrid). Companion to the cross-provider parity reference: same N-row scorecard shape, different layer (TPipe orchestration containers instead of LLM provider modules). Captures the 2026-08-08 audit's full kill list: 5 dead private fields, 11 interface no-op stubs in P2PInterface, 13 emitted-but-unconsumed trace events (especially `KILLSWITCH_TRIPPED`), 2 declared-but-unemitted events (`PAUSE_POINT_CHECK`, `PIPE_TIMEOUT`), ~10 dead function parameters, plus the malformed filename at `Pipeline.kt:873` (literal extension token embedded in middle of name = clear signal the autoExport path was never run end-to-end). Two new pitfalls surfaced: "consumer-site count IS the parity scorecard" (when a contract has both a config site and a builder site, also enumerate the consumers) and "empty-body interface defaults silently no-op when implementers forget to override" (convert to `abstract` to let the compiler enforce).
- `references/2026-08-08-trace-config-maxhistory-tdd-closure.md` — the FIX-side companion to the cross-container parity audit. Captures the full RED-GREEN-REFACTOR closure of the `TraceConfig.maxHistory` gap (2-of-6 → 6-of-6 containers), including the test seam (`internal fun getMaxHistoryForTest()`), the 6 surgical one-line patches with per-container surrounding context, the JUnit XML verification pattern, and the docs patch that removed the incorrect "not used" claim from `docs/core-concepts/tracing-and-debugging.md`. The canonical worked example for the "Closing a cross-container parity gap with TDD" section above.
- `references/2026-08-08-trace-config-autoexport-tdd-closure.md` — the FIX-side companion to the cross-container parity audit for the **thread-safe** autoExport closure. Captures the `TraceAutoExporter` design (per-path `ReentrantLock` map, hard-deadlock-free by construction), the test-seam taxonomy that surfaced (reader / ID / producer seam), the 4 thread-safety tests + 8 container-propagation tests + 1 malformed-filename regression test (13 tests total), the missing-API additions (`getTraceId` on DistributionGrid + MultiConnector; `getTraceReport` on Connector + MultiConnector; `setRunIdForTest` on PumpStation), the scope-narrowing workflow rule, and the doc-claim contradiction pattern (patch `docs/core-concepts/tracing-and-debugging.md:90` from "not used" to "honored by every container"). The canonical worked example for the "Closing a thread-safe auto-export parity gap with TDD" extension.
