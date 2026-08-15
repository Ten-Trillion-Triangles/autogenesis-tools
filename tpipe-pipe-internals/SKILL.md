---
name: tpipe-pipe-internals
description: |
  Reference for the TPipe Pipe class lifecycle, DITL hook points, and reasoning-content lifecycle. Load when investigating how Pipe.execute() flows, when wiring hook callbacks for outer scaffolding (agent harnesses, observability, content transformation), or when reasoning about where to observe the final MultimodalContent before it bubbles to a parent pipe. ALSO LOAD when investigating "pipe context not flowing from X to Y" — the context-pull builders (pullGlobalContext, pullPipelineContext, pullParentPipeContext, pullPumpStationContext) each flip a flag, but only some flags have an execution-time read site. ALWAYS LOAD when investigating "does feature X reach the wire?" — pipe state splits across three surfaces (user role in content.text, system role in pipe.systemPrompt, wire body inside generateText), and a complete reach audit captures all three.
version: 1.6.0
metadata:
  hermes:
    tags: [tpipe, pipe, ditl, hooks, lifecycle, reasoning, multimodal-content, context, pumpstation, pull-builder, wire-reach]
    related_skills: [tpipe-pipeline-patterns, tpipe-reasoning-pipes, tpipe-json-serialization]
---

# TPipe Pipe Class Internals

## Changelog

- **1.7.0 (2026-08-04)** — Added "Pipe setter fluency split" pitfall and "Consumer-side instantiation via `DummyPipe()`" section. Captured from the TPipe 1.0.15 fresh consumer bootstrap: `Pipe` is abstract (no public constructor — only `protected`-scoped compile-time-no-arg path); the no-arg concrete entrypoint consumers use is `com.TTT.Pipe.DummyPipe extends com.TTT.Pipe.Pipe`. Among the 80+ `set*` setters on `Pipe`, some return `Pipe` (chainable) and some return `void` (must be statements) — known void setters at TPipe 1.0.15: `setPipeRole(PipeRole)`, `setPipeTimeout(long)`, `setEnablePipeTimeout(boolean)`, `setApplyTimeoutRecursively(boolean)`, `setKillSwitch(KillSwitch)`. Verification recipe included: `javap -classpath <published-jar> -public com.TTT.Pipe.Pipe | grep 'public.*set[A-Z]'` BEFORE writing any consumer-side fluent chain. Description widened to load the skill on fresh consumer bootstrap.
- **1.5.2 (2026-07-31)** — Added "Footer-prompt reach has two paths, both verify-able" pitfall. Path A (Pipe.kt:2560-2563) is unconditional: `applySystemPrompt()` appends `pipe.footerPrompt` to `pipe.systemPrompt` whenever non-empty. Path B (Pipe.kt:8047) is gated: `getFooterPromptForReasoning()` reads `reasoningPipe?.pipeMetadata["injectFooterPrompt"]` and is used at Pipe.kt:7136/7201 to assemble the HOST's developer prompt. The Mantle helper (GenericOpenAIPipe.kt:680-682) closes Path B by default. Path A still fires on the reasoning pipe's own systemPrompt — do not dismiss `setFooterPrompt(...)` as dead code on Mantle reasoning pipes. Also added the "substring false-positive on assertion message text" pitfall: a probe that greps for a JSON field name in a captured failure message will false-positive on the assertion message itself, which usually contains the same word. Extract just the captured JSON body before grepping. Updated `references/wire-reach-investigation.md` with the footer-prompt case study.
- **1.5.1 (2026-07-30)** — Added pointer to `references/wire-reach-investigation.md` (companion session-applied reference for the wire-reach investigation pattern captured in section 1.5.0).
- **1.5.0 (2026-07-30)** — Added "Pipe-state probes for 'does X reach the wire?' investigations" section. Captures the three-surface split (user role in `content.text`, system role in `pipe.systemPrompt`, wire body inside `generateText`) that makes wire-reach audits complete, plus the `supportsNativeJson` gate that controls whether the JSON-prompt-injection augmentation at Pipe.kt:2108-2257 fires. Includes the control-case pattern (Mantle validator pipe vs Mantle author pipes) that maps defect asymmetry to fix surface (TPipe vs consumer factory). Description widened to load the skill on "does feature X reach the model wire?" investigations.
- **1.4.0 (2026-07-29)** — Added "The validator-pipe / branch-pipe slot pattern" section: documents the Pipe-slot gate-and-fallback pattern (`setValidatorPipe(Pipe)` + `setBranchPipe(Pipe)`) verified by extracting `com.TTT.Pipe.Pipe` from `libs-local/TPipe-1.0.0.jar`. This is a class of pipe-attached pipes distinct from DITL lambdas (`validatorFunction`/`transformationFunction`) and from Pipeline/Splitter composition — the `validatorPipe` slot invokes a *whole Pipe* as the validator, and the `branchPipe` slot is the fallback that runs when the validator fails. Captures the three production factory styles in Autogenesis (`buildTPipeValidatorPipe`, `buildBranchFailureAgent`, `buildBranchPipeFromTemplate`) plus the private inline `buildPalmyraFallbackAgent` in `judgeOutcome/npcJudge.kt:81`, and the orchestrator-level wiring pattern (`Splitter.addPipeline` for parallel validators, `Pipeline.add` for chained gate-then-repair). Generalizes the lesson: when a setter takes a `Pipe` (not a lambda), it is a separate execution lane with its own model / token budget / reasoning pipe — copy the configuration forward explicitly, or the slot is silently under-configured.
- **1.3.0 (2026-07-24)** — Added pitfall "Path-name map keys and lookup keys must agree — the case-insensitive contract is enforced at the map boundary, not by the lookup helper." Sibling case to the pull-builder pitfall below: the KDoc on `PumpStation.pathList` and `PumpStationHelpers.resolvePath` has always promised case-insensitive path lookup, but `addPath` stored `pathList[path.pathName]` (case-preserved) while `resolvePath` looked up `pathList[name.lowercase()]` (lowercased). The 2026-07-24 live-04 trace showed 19 consecutive `PathFailed` events with `errorMessage: "Path 'giveUp' not found"` because the LLM picked a camelCase path name from a visible-paths menu that the runtime couldn't resolve. The fix is the `pathKey(name)` helper in `Pipeline/PumpStation.kt` that lowercases every map key on insert AND on lookup, while `getVisiblePathNames()` reads the original-cased `path.pathName` field for display. Six production sites + the `revealedReservePaths` set all route through the helper. The lesson is the same shape as the pull-builder pitfall below: a documented contract with no enforcement at the data-structure boundary silently breaks for half the input space (in this case, any non-uppercase path name). The test pinning recipe is the `PumpStationPathCaseInsensitiveTest` class (6 tests, all green as of 2026-07-24).
- **1.2.0 (2026-07-22)** — Added pitfall "Context-pull builders are NOT guaranteed to fire — verify the merge order." Captured the `pullPumpStationContext()` dead-builder defect: the flag is declared and the setter exists, but `executeMultimodal` never reads it. Commit `a84a91b8 expand p2p interface` added the consumer-side infrastructure (`getContextWindowFromInterface`, `getMiniBankFromInterface`, PumpStation overrides) but missed the wiring inside `executeMultimodal`. Includes a per-builder truth table, grep-based verification recipe, fix surface (with deep-copy rationale), and test-pinning recipe. Description widened to load the skill on "context not flowing" investigations.
- **1.1.0** — Initial public release.

## When to load

**TL;DR — also load when planning a TPipe factory return-type migration.** If a production factory like `buildTPipeValidatorPipe(...): BedrockMultimodalPipe` is being migrated to return a different `Pipe` subclass (`GenericOpenAIPipe` for a Mantle switch, `OllamaPipe` for a local switch, or any cross-provider swap), the return-type change is INVISIBLE at call sites IF the slot setter takes the abstract `Pipe` type. `setValidatorPipe(Pipe)` and `setBranchPipe(Pipe)` both take the base type, so no `setValidatorPipe(buildTPipeValidatorPipe(...))` call site needs to change. Verify by `javap -public com/TTT/Pipe/Pipe.class | grep -E 'setValidatorPipe|setBranchPipe'` before assuming call-site refactors are needed. Captured 2026-07-29 on the Autogenesis validator-pipe migration: `buildTPipeValidatorPipe` (30+ call sites) was migrated from `BedrockMultimodalPipe` to `GenericOpenAIPipe` — zero call sites needed editing. Without the verifier the agent would have proposed updating 30+ `.apply { ... }` chains, propagating the type change into every agent file. See the new pitfall at the end of this skill for the full recipe and the 30-second verification.

**TL;DR — also load when investigating "does feature X reach the model wire?"** Pipe state splits across three surfaces: user role (`MultimodalContent.text` via `preInvokeFunction`), system role (`pipe.systemPrompt` via `pipe.getSystemPromptText()` post-execute), wire body (HTTP request body inside `generateText()`). `applySystemPrompt()` rebuilds `pipe.systemPrompt` but does NOT mutate `content.text`, so a probe that only attaches `preInvokeFunction` will see ONLY the user role. JSON schema rails, footer prompts, and middle-prompt injection live on the system role and are invisible from pre-invoke. The `supportsNativeJson` flag (Pipe.kt:1100) gates the JSON-prompt-injection augmentation at Pipe.kt:2108-2257 — `requireJsonPromptInjection()` sets it to `false`. See "Pipe-state probes for 'does X reach the wire?' investigations" below for the full recipe, and `references/wire-reach-investigation.md` for the case study + verifier pattern.

**TL;DR — also load when bootstrapping a fresh consumer Gradle project against a TPipe-shaped artifact.** Two consumer-side compile failure modes that look like API bugs but are property of the bytecode surface: (a) `Pipe` is abstract — the no-arg concrete entrypoint is `com.TTT.Pipe.DummyPipe extends com.TTT.Pipe.Pipe` with `public DummyPipe()`; consumers ALWAYS instantiate `DummyPipe()` and assign up to `val pipe: Pipe`. (b) Some `set*` setters are fluent (return `Pipe`, chainable) and some are void (return `void`, must be called as statements) — see the "Pipe setter fluency split" section below for the bytecode-verification recipe and the known-void-setter list. Captured 2026-08-04 on a TPipe 1.0.15 fresh consumer bootstrap.


## When to load (full)


- Investigating the Pipe class execution lifecycle
- Choosing the right hook to observe or mutate content (DITL hooks)
- Reasoning about where `modelReasoning` lives in the content object
- Building outer scaffolding (agent harnesses, observability) that wraps Pipe
- Verifying whether a TPipe feature actually reaches the wire (model-reach / injector-reach audits)

## Pipe-state probes for "does X reach the wire?" investigations

When the question is "does [pipe-level feature] actually reach the model wire?" the answer is rarely visible from a single observation point. The pipe lifecycle splits state across three surfaces, and a complete audit captures all three:

| Surface | Where | When visible |
|---|---|---|
| User role | `MultimodalContent.text` (via `preInvokeFunction`) | Before LLM call, in `executeMultimodal` |
| System role | `pipe.systemPrompt` (via `pipe.getSystemPromptText()`) | After `applySystemPrompt()` rebuilds it |
| Wire body | HTTP request body sent to provider | Only inside `generateText()` or the streaming equivalent |

`applySystemPrompt()` (Pipe.kt:2250-2569) rebuilds `pipe.systemPrompt` but does NOT mutate `MultimodalContent.text`. The system prompt is stored on the pipe and read by the request serializer; the user prompt lives in `content.text`. A probe that only attaches `preInvokeFunction` and captures `content.text` will see ONLY the user role — the JSON schema rail, footer prompt, and middle-prompt injection live on the system role and are invisible from that hook.

For a "schema reaches the wire" investigation, capture BOTH:

```kotlin
.setPreInvokeFunction { content -> capturedUserPrompt.append(content.text); true }
// ... execute ...
val systemPromptAfter = pipe.getSystemPromptText()  // Pipe.kt:4882
```

The wire body itself is not observable from a test without intercepting HTTP. Use a `HttpURLConnection`-level test fixture or a `WireMock` server for that surface. The Mantle / OpenAI-compat path's `response_format = {"type": "json_object"}` field lives only on the wire body and is invisible to `getSystemPromptText()`.

### Control-case pattern for pipe-level reach audits

When the question is "does feature X work for provider P?", find an existing call site where X works and use it as the control. The asymmetry between control and failing cases maps directly to which API surface the fix belongs on.

For the Mantle / Gemma JSON-adherence investigation (2026-07-30):

- **Working control**: `mantle validator pipe` at `ValidatorPipeAgent.kt:89-90` — Bedrock host pipe (NOT Mantle factory) that wires `requireJsonPromptInjection + setJsonOutput` at the agent layer, then attaches Mantle reasoning pipe via `setReasoningPipe(...)`. This works because it bypasses the Mantle factory's bug surface.
- **Failing cases**: `mantle author 31b`, `mantle writing pipe (g31b)`, `mantle structured cot` — Mantle-routed pipes built via `BedrockConfig.buildMantleAuthorPipe` / `buildMantleReasoningPipe`. These skip the JSON contract at the factory level.

Decision tree:
- If the working control wires the contract at the agent layer and the failing cases skip it at the factory layer → fix is in the factory, NOT in TPipe.
- If BOTH the control and failing cases wire the contract and the wire body still differs → fix is in TPipe (provider-side serializer, request body mapping, or pipe lifecycle).

### `supportsNativeJson` is the JSON-prompt-injection gate

`Pipe.supportsNativeJson` (Pipe.kt:1100, default `true`) gates the JSON-requirements block augmentation at Pipe.kt:2108-2257. `requireJsonPromptInjection()` (Pipe.kt:2865-2868) sets it to `false`. The wire-format completion hook at `GenericOpenAIPipe.onApplySystemPromptComplete` (TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:407-414) is gated by the same flag — when `supportsNativeJson = true`, the hook returns early and `responseFormat` stays null.

When auditing a pipe for "JSON-mode enforcement reach," check the `supportsNativeJson` field BEFORE assuming the wire-format hook is firing. The flag is `protected` (Pipe.kt:1100) and not directly readable from outside the package; the proxy is whether `requireJsonPromptInjection()` was called (it sets the flag to `false`).

### Three-probe shape that pins "X does not reach the wire" cleanly

A wire-reach investigation produces actionable evidence when three probes run together:

1. **Structural probe (no network)** — instantiate the pipe via the production factory and assert on the public pipe surface (`pipe.jsonOutput`, `pipe.jsonInput`, `pipe.pipeMetadata`, `pipe.reasoningPipe`, `pipe.getSystemPromptText()`). Today's assertions fail because the factory didn't wire the contract. This is the cheap diagnostic.

2. **Live wire probe (network, gated)** — attach `preInvokeFunction` to capture `content.text`, run `pipe.execute(testPrompt)`, and assert that the captured user prompt + `pipe.getSystemPromptText()` carry the expected rail. This is the proof.

3. **Working-control probe (network, gated)** — find the working call site in production code, replicate its wiring shape against the failing factory, and assert the rail reaches. If it does, the bug is in the factory (skipping the wire-up). If it doesn't, the bug is in TPipe (despite the wiring).

The three probes map to the three receivers in the verifier at `/tmp/hermes-verify-mantle-injector-reach.sh` (template structure reusable for any wire-reach audit). Full case study + scaffolds in `references/wire-reach-investigation.md`.

### Footer-prompt reach has two paths, both verify-able (2026-07-31)

Footer prompt reach is NOT a single path. Two distinct code paths can carry `pipe.footerPrompt` to the wire, and they have different gates:

| Path | Location | Gate | Fires on |
|---|---|---|---|
| Path A (unconditional) | `Pipe.applySystemPrompt()` at Pipe.kt:2560-2563 | None — `if(footerPrompt.isNotEmpty()) systemPrompt = "$systemPrompt \n\n $footerPrompt"` | Every pipe's own system prompt, every execute cycle |
| Path B (gated) | `getFooterPromptForReasoning()` at Pipe.kt:8047, called at Pipe.kt:7136 and 7201 | `reasoningPipe?.pipeMetadata["injectFooterPrompt"] as? Boolean ?: false` | HOST's developer prompt when assembling converse-history JSON for a reasoning-pipe call |

The Mantle helper `GenericOpenAIPipe.configureBedrockMantle` (GenericOpenAIPipe.kt:680-682) closes Path B by default by setting `pipeMetadata["injectFooterPrompt"] = false`. This prevents the Mantle reasoning pipe's footer from being injected BACK into the host's developer prompt — the right default because the host and reasoning pipe are independent pipe objects with independent footer text, and the JSON-completion suffix from `ReasoningBuilder.assignDefaults` would otherwise leak into pipes that don't want it.

But Path A still fires. When a Mantle reasoning pipe has `setFooterPrompt(text)` set by the caller, `applySystemPrompt()` runs inside the reasoning pipe's own `execute()` and unconditionally appends `text` to the reasoning pipe's `systemPrompt`. The reasoning pipe's outgoing wire body then carries the footer text on its own system role, independent of the Path B gate.

**Lesson**: do not dismiss `setFooterPrompt(...)` as dead code on Mantle reasoning pipes. The Mantle helper closes Path B (the host's developer prompt), but Path A (the reasoning pipe's own system prompt) is unconditional. Probes that read `pipe.systemPrompt` of the REASONING pipe (not the host) AFTER `host.execute()` returns will see the footer text via Path A.

Probe recipe for footer-prompt reach (verify both paths independently):

```kotlin
// Path A (unconditional) — read reasoningPipe.systemPrompt AFTER host.execute()
val reasoningSysPrompt = reasoningPipe.getSystemPromptText()
assertTrue(reasoningSysPrompt.contains(footerText), "Path A unconditional — footer must reach reasoning pipe's systemPrompt")

// Path B (gated) — affects host's developer prompt. Verify gate behavior by
// checking whether the footer appears in the host's systemPrompt only when
// injectFooterPrompt=true was set on the reasoning pipe.
```

### Substring false-positive on assertion message text (2026-07-31)

When a probe captures the failure message as the wire-payload evidence (via grepping the JUnit XML for "Got first 400 chars: '...'"), naively grepping the captured fragment for a JSON field name can false-positive — the assertion message itself contains the field name as the expected-shape text. Example:

```kotlin
// Test asserts on the field name "verdict" — assertion message contains "verdict":
assertTrue(outgoingPrompt.contains(SCHEMA_FIELD, ignoreCase = true),
    "Reasoning pipe's outgoing prompt must contain the host's JSON schema field 'verdict' ...")
// → failure message reads "...must contain the host's JSON schema field 'verdict'..."
// → naive grep on the captured fragment finds "verdict" inside the message text, not the payload
```

**Fix**: extract only the captured body (the actual JSON or text that the assertion is gating on), not the whole failure message. For JSON captures, bracket-match on `'\{...'` after the leading "Got first 400 chars: '" prefix. For text captures, anchor on a known delimiter that appears only in the body. When the capture format doesn't naturally delimit body from message, anchor on the suffix `"Got first"` and use `head -c` to truncate.

`references/wire-reach-investigation.md` includes both path-A and path-B footer verification probes plus the substring-false-positive workaround.

## The 8 DITL hooks (lifecycle ordering)