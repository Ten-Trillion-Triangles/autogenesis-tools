# Cross-Repo Streaming Parity Triage (SDK ⇄ Consumer)

A class of work that does NOT fit a single repo or a single
test-driven development cycle: when a cross-cutting feature
(streaming, citations, guardrails, prompt caching) is rolled
out across **two repos** — the SDK provider (TPipe) and the
consumer (e.g. Autogenesis) — and you need to know whether the
feature actually reaches the wire end-to-end.

The trap: the SDK may have the feature fully wired and tested
(green), the consumer may have the feature half-wired (some
agents stream, some don't), and a single repo's report (TPipe
green OR Autogenesis green) is misleading either way. The
"streaming works" claim is a **relation** between two repos,
not a fact within either one.

## When to use this methodology

- The user asks "triage X" / "audit X" / "verify X is set up
  correctly" for a cross-cutting feature that touches two
  repos with a provider-consumers relationship.
- The same feature name means different things on each side.
  In streaming: SDK side = `setStreamingCallback` registers
  with the manager; consumer side = per-agent `setStreamingCallback`
  wires the manager to the dispatcher's appendChunk.
- The user has explicitly named hand-off semantics: "if the
  SDK side is incomplete with no unit test, handoff to another
  agent; if complete, fix the consumer side here". This is the
  signal that the output is a **binary verdict per repo**, not
  a single audit.

Do NOT use when:

- The feature lives in one repo only. Just audit that repo.
- You have direct edit access to both repos. Fix both at once.
- The user wants a generic feature audit (use the parent
  skill's four-pass audit methodology instead).

## The four-cell gap matrix

Produce a **four-cell matrix** at the end of the triage, not a
narrative. Each cell says "right" or "broken" with evidence:

| Cell | SDK side (provider) | Consumer side (using repo) |
|---|---|---|
| **Prim-surface** | `setStreamingCallback` exists on the provider pipe class | Per-agent calls to `setStreamingCallback` exist |
| **Wire-surface** | Streaming chunks arrive at `emitStreamingChunk` → manager → callback | Callback fires `dispatcher.appendChunk(...)` on the right channel |
| **Test-surface** | Unit + live tests pin the surface | Live integration tests pin the consumer wiring |
| **Hand-off** | All three SDK cells green means SDK is done | All three consumer cells green means consumer is done |

A cell is `"right"` if it has a passing test OR an explicit
verified-by-evidence reference. A cell is `"broken"` if it's
absent, has a commented-out implementation, or has no test.

## The two-repo workflow

### Step 1 — categorize the surface first

Before reading any code, list the four-cell axes for the
feature and the two repos. For streaming:

```
SDK side:                Consumer side:
  prim: setStreamingCallback  per-agent: setStreamingCallback
  wire: emitStreamingChunk    dispatcher: appendChunk
  test: SSE parsing + live     live: Mantle → dispatcher
```

The cells are PAIRS across the two repos. Each pair answers
one question: "does the feature actually reach the user's UI?"

### Step 2 — read the SDK side first

Walk the SDK source tree systematically:

1. **Locate the streaming primitive on the provider pipe class.**
   For Bedrock: `enbleStreaming()` + `setStreamingCallback()` +
   `streamingCallbacks { add(...) }` builder. For Mantle:
   `setStreamingEnabled()` + `setStreamingCallback()` only — no
   builder DSL. **The absence of the builder DSL is a real gap,
   not a style preference** — it means consumers can't use
   `enableStreaming().streamingCallbacks { add(f1); add(f2) }`
   the way they do on Bedrock.
2. **Trace the streaming exec path.** Find `executeStreaming` /
   `executeStreamingDirect` / `executeStreamingAnthropic` etc.
   Confirm each path calls `emitStreamingChunk(delta)` per SSE
   line. Confirm the request includes `"stream": true` in the
   JSON body.
3. **Find the streaming tests.** Group them by class:
   - Unit tests (no network): SSE parsing, reasoning capture,
     callback registration contract.
   - Live integration tests (gated on env vars): bearer
     streaming, SigV4 streaming, chunked streaming, reasoning
     streaming.
4. **Cross-reference the test list against the SDK's
   provider surface.** A live test that runs streaming but
   doesn't register `setStreamingCallback` doesn't pin the
   callback delivery path — it only pins the wire-content path.
   These are NOT equivalent verifications.

The SDK side has a binary verdict: **all four cells (Bedrock
prim, Bedrock wire, Mantle prim, Mantle wire) have passing tests
that exercise the streaming callback delivery path** → SDK is
done. Any cell missing a callback-delivery test means the SDK
side has a verification gap, even if the rest is green.

### Step 3 — read the consumer side second

Walk the consumer code tree:

1. **Locate the streaming dispatcher.** Find the function
   that receives a chunk and routes it to the user-visible
   surface (UI panel, AgentWorkStream, websocket DELTA event).
   Call it `dispatcher.appendChunk(connectionId, chunk)`.
2. **Find every call site of `setStreamingCallback` /
   `streamingCallbacks { add(...) }` / `setStreamingEnabled`
   across the consumer's pipe builders.** Classify each:
   - **Wired correctly**: the callback routes to the dispatcher.
   - **Flag set, callback missing**: `setStreamingEnabled(true)`
     with no callback. The Mantle pipe runs in streaming mode
     but no listener catches the chunks. **Silent no-op.**
   - **No streaming at all**: pipe runs in batch mode. Final
     result arrives all at once.
   - **Bedrock-only factory**: a function that wraps
     `pipe.enableStreaming().streamingCallbacks { ... }` —
     fails on a non-Bedrock pipe because the DSL doesn't exist.
3. **Find the orchestrator-level streaming extensions.**
   Functions like `enableBufferedNarrativeStreaming(throttler:
   NarrativeChunkThrottler)` that are typed as `BedrockPipe`
   receiver. These never fire on a non-Bedrock pipe.
4. **Find the streaming-flag-without-callback sites.** Run
   `grep -n "setStreamingEnabled\|enableStreaming"` and look
   for files where the flag is set but no callback is wired
   nearby. These are the silent no-ops.

The consumer side has a per-agent verdict: **for each agent
with a migrated-to-Mantle pipe, does the callback route to the
dispatcher?** Any agent with streaming-flag-but-no-callback
is a silent no-op.

### Step 4 — produce the gap matrix

The output is a four-cell matrix with explicit per-cell evidence
and a binary verdict per repo:

```
SDK side verdict: COMPLETE / INCOMPLETE
  prim: ✓ Bedrock + Mantle have setStreamingCallback
  wire: ✓ emitStreamingChunk routes through manager
  test: ✓ bearer + SigV4 + chunked + reasoning streaming tests
  verdict: SDK is complete; no TPipe handoff needed

Consumer side verdict: BROKEN
  prim: 7 of 8 LOW agents have no setStreamingCallback wired
  wire: 1 of 8 has a callback (OpenWidgetAgent.pcpPipe)
  test: 0 live integration tests pin Mantle → dispatcher
  fix: agent-side wiring for the 7 missing agents
```

### Step 5 — separate the work by repo

The whole point of the cross-repo triage is to know which
repo holds the work. The two-repo handoff semantics:

- If SDK is incomplete, **hand off**: produce a separate
  follow-up task in the SDK repo. Don't fix it inline.
- If SDK is complete and consumer is broken, **fix inline**:
  the consumer-side work is right here.
- If both are broken, hand off SDK first, then fix consumer
  once SDK is green.

The user will explicitly say which side to fix when the
report is delivered. The triage above is the basis for their
decision.

## Three pitfalls

### 1. Conflating "streaming works" with "wire test passes"

A live test that calls `setStreamingEnabled(true)` and asserts
the response TEXT contains "pong" passes even when chunks
never reach the callback. The wire test verifies content
arrival; it does NOT verify callback delivery. To verify
callback delivery, the test must register a callback and
inspect its captured chunks.

A common false-positive pattern: a Bedrock live test that uses
the Bedrock-only `streamingCallbacks { add(...) }` DSL. The
test passes on Bedrock. Mantle pipes don't have that DSL. A
producer who copies the test pattern verbatim onto a Mantle
test will see compile errors at the DSL site, not at the
streaming flag — the failure mode is opaque.

### 2. The Bedrock `streamingCallbacks` builder is not portable

There is no `streamingCallbacks { add(...) }` DSL on
`GenericOpenAIPipe` (Mantle) at the time of writing. The
mantle provider has only the single-callback
`setStreamingCallback(cb)` shape. Consumers who write
streaming wiring in the Bedrock DSL against a Mantle pipe
will hit compile errors at the `.streamingCallbacks { ... }`
call site.

A typical cross-provider reflex is to assume "streaming is
streaming" and use the same fluent chain on every provider.
**It is not.** Each provider pipe has its own streaming
surface; the consumer-side code must dispatch on `pipe is
GenericOpenAIPipe` vs `pipe is BedrockMultimodalPipe`. A
generic `pipe.enableStreaming().streamingCallbacks { ... }`
helper will compile on Bedrock and fail on Mantle.

### 3. The "flag set, callback missing" failure mode is silent

A `setStreamingEnabled(true)` call without a callback means
the pipe runs in streaming mode but no listener catches the
chunks. The pipe still completes; the final response arrives
all at once. The user sees the result, just not streamed.

There is no error signal. There is no trace event. There is
no missing-chunk log. The pipe's `executeStreaming()` returns
successfully with all chunks concatenated into the final
text. The streaming flag is set; the API stream is consumed;
the callback list is empty.

To detect this: grep for `setStreamingEnabled` and `enableStreaming`
in the consumer code, then for each match, check the surrounding
20 lines for a `setStreamingCallback` or `streamingCallbacks {`
DSL call. If not present, the flag is set in a vacuum.

## Worked example: Mantle streaming on Autogenesis

The 2026-07-30 session on Autogenesis produced this exact
triage shape. The user asked "triage if we've setup and
correctly handled streaming for the mantle pipes so that it
works exactly as it should and does with bedrock in the game's
system."

The four-cell matrix was:

| Cell | Verdict | Evidence |
|---|---|---|
| SDK prim | ✓ right | `BedrockPipe.enableStreaming() + setStreamingCallback() + streamingCallbacks { add(...) }` builder; `GenericOpenAIPipe.setStreamingEnabled(true) + setStreamingCallback()` |
| SDK wire | ✓ right | `executeStreaming()` / `executeStreamingDirect()` both call `emitStreamingChunk(delta)` per SSE; `streamingEnabled` flag flips `"stream": true` in the request body |
| SDK test | ✓ right (with one narrow gap) | `MantleSseFixtureReplayTest` (unit) + `BedrockMantleLiveTest.testBearerStreamingChatCompletions` + `testBearerStreamingResponses` + `testChunkedSigV4Streaming` + `testMantleStreamingWithReasoning` + `MiniMaxFeaturesLiveTest` (callback delivery) + `AnthropicStreamingLiveTest` (callback delivery). Narrow gap: SigV4 streaming + callback delivery is not tested in a single test (chunked SigV4 asserts content; callback tests are bearer-only). |
| Consumer prim | ✗ broken | 7 of 8 LOW agents have zero `setStreamingCallback` calls; `ResponseRefinementAgent` has `setStreamingEnabled(true)` (flag) but no callback (silent no-op) |
| Consumer wire | ✗ broken | Orchestrator's `enableBufferedNarrativeStreaming(throttler)` is typed `BedrockPipe` receiver; never fires on Mantle pipes |
| Consumer test | ✗ broken | Zero live integration tests pin Mantle → dispatcher |

The two-repo verdict: SDK complete (with narrow gap), consumer
broken. The SDK gap is 1 hour of work (one test method). The
consumer work is 6-8 hours (per-agent callbacks + refactor
orchestrator extractor + 1 live integration test).

## Cross-references

- `tpipe-pipe-feature-audit` (parent) — the four-pass audit
  methodology for SINK-side "does this feature actually fire?"
  questions. This reference covers the SOURCE-side and
  cross-repo extension.
- `tpipe-pipe-internals` — the parent class-level skill for Pipe
  internals. The base `obtainStreamingCallbackManager` /
  `emitStreamingChunk` / `propagateStreamingCallback` are
  documented there.
- `tpipe-test-patterns` — TPipe test patterns including how
  to write a callback-delivery verification test using a
  capture list.
- `tpipe-reasoning-pipes` — the `setReasoningPipe` boundary
  where features silently don't propagate. The reasoning pipe
  has its own independent state; if the main pipe is wired
  for streaming but the reasoning pipe is not, the reasoning
  pipe's chunks go nowhere.
- `model-and-tier-policy-audit` — the two-axis verification
  pattern for cross-cutting provider-config changes. The streaming
  audit is a sibling methodology: cross-cutting feature audit
  across two repos, minting a four-cell matrix.
- `references/2026-07-29-bedrock-mantle-streaming-reasoning-round3.md` —
  the SINK-side pitfall that ships alongside this cross-repo
  triage: openAI-compatible providers can emit shortened event
  names that the parser dispatch table doesn't recognize. Captures
  the Mantle `response.reasoning.delta` / `.done` short-form
  extraction that had to be added to the parser.
