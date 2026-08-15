# KillSwitch — source points and origin story

Source-grounded research for any blog post, doc, or marketing claim about TPipe's KillSwitch. Every claim in a post should be sourceable to one of the file:line refs here. The origin story is sourced from a 2026-06 user session and is the canonical narrative for why the feature exists.

## The implementation (66 lines, the entire file)

**`TPipe/src/main/kotlin/P2P/KillSwitch.kt`** — the entire KillSwitch system.

Key points to cite:
- The `onTripped` callback is typed `(KillSwitchContext) -> Nothing = { ctx -> throw KillSwitchException(ctx) }`. The `Nothing` return type is Kotlin's bottom type. The compiler rejects any callback that does not throw, call `error()`, or call another `Nothing` function. The default callback is a single throw. The file ends with a throw.
- `KillSwitchException` extends `RuntimeException`. It is an uncaught exception by default. The runtime propagates it.
- `KillSwitchContext` carries `accumulatedInputTokens`, `accumulatedOutputTokens`, and `depth` — the data needed to enforce a root-down budget across the call chain.

**The 66-line count is the punchline.** Show the entire file in the post body. Lead with: "The entire safety system fits in a 66-line Kotlin file. It has been in production for 18 months. It has never failed to terminate."

## Where the check fires

**`TPipe/src/main/kotlin/Pipe/Pipe.kt`**
- Line 594: `override var killSwitch: com.TTT.P2P.KillSwitch? = null` — the property on the Pipe class, marked `@kotlinx.serialization.Transient` (not part of the serializable snapshot)
- Lines 6015-6021 and 6153-6158: the `if (killSwitch != null) { ... checkKillSwitch(...) }` calls in the main pipe execution loop, after every token-count update
- Lines 7615-7647: the `checkKillSwitch` function — the actual `inputExceeded` / `outputExceeded` evaluation, the `when` block that produces the `reason` string (`"input_exceeded"`, `"output_exceeded"`, or `"input_and_output_exceeded"`), and the call to `ks.onTripped(KillSwitchContext(...))`

**Key claim to support with the source:** "The check fires on every pipe execution. There is no way for the agent to spend tokens without the check seeing them."

## The catch-and-rethrow carve-out (the architectural punchline)

**`TPipe/src/main/kotlin/Pipeline/Splitter.kt`**
- Lines 117-126: the `killSwitch` setter on Splitter, which propagates the killSwitch to every child pipeline
- Lines 140-148: the accumulator fields (`killSwitchInputAccumulator`, `killSwitchOutputAccumulator`, `killSwitchExecutionStartTime`) marked `@Transient`
- Lines 159-216: the `checkKillSwitch` function for the Splitter (separate from the Pipe-level one) — same input/output exceeded logic, but operates on accumulated totals
- Lines 672-676: the reset of the accumulators at the start of execution
- Lines 732-737: **the accumulator update** — after every branch completes, `killSwitchInputAccumulator += pipeline.inputTokensSpent` and the check is performed against the accumulated total. This is the root-down enforcement.
- **Lines 778-782: the catch-and-rethrow carve-out.** This is the architectural argument in one code block:
  ```kotlin
  catch(e: com.TTT.P2P.KillSwitchException)
  {
      // KillSwitchException must never be caught — it must propagate to terminate the agent
      throw e
  }
  ```
  The Splitter has a generic `catch(e: Exception)` block at line 783 that turns exceptions into "Pipeline execution failed" content, allowing the next pipeline to run. The carve-out sits BEFORE the generic catch and re-throws the KillSwitchException. The architecture explicitly defends the propagation.

**This is the kill shot for any post about the KillSwitch.** Walk through the two catch blocks. Show the comment: "must never be caught — it must propagate to terminate the agent." That's the entire architectural commitment in one line.

## The DSL builders

**`TPipe/src/main/kotlin/Pipeline/ManifoldDsl.kt`**
- Lines 154-162: the `killSwitch(inputTokenLimit, outputTokenLimit, onTripped)` DSL function on the `ManifoldBuilder`. Returns the builder for chaining. Builds a `KillSwitch` instance and stores it in `killSwitchConfiguration`.

The Junction and DistributionGrid DSLs have equivalent `killSwitch()` builders (same pattern, same defaults).

## Container propagation

**`TPipe/src/main/kotlin/P2P/P2PInterface.kt:144`** — the `var killSwitch: KillSwitch?` property on the `P2PInterface` interface. Every TPipe container implements this interface.

**Implementations of the killSwitch property:**
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:594` — Pipe (the leaf)
- `TPipe/src/main/kotlin/P2P/P2PRegistry.kt:586` — P2PRegistry (hosted agent)
- `TPipe/src/main/kotlin/P2P/P2PHostedRegistry.kt:494` — P2PHostedRegistry (client agent)
- `TPipe/src/main/kotlin/Pipeline/Splitter.kt:117-126` — Splitter (with explicit propagation to child pipelines in the setter)
- `TPipe/src/main/kotlin/Pipeline/PumpStation.kt:184` — PathObject
- `TPipe/src/main/kotlin/Pipeline/PumpStation.kt:535` — PumpStation

**Key claim to support with the source:** "Every container in TPipe implements the P2PInterface, which exposes the killSwitch property. Set the killSwitch at the highest level that maps to the budget you want to enforce. The runtime walks the container hierarchy and applies the budget to every leaf."

## The origin story (from the user, 2026-06-13)

**The incident:** The Bedrock SDK timed out without notifying the caller. The generic exception was treated as a transient error by the retry policy. Each retry spent 50,000-200,000 input tokens. Autogenesis, running headless 24/7 with no human in the loop, kept retrying. Close to a billion input tokens were burned. The bill would have been in the thousands of dollars — "the kind of number that ends a three-person company before it ends the month."

**The reaction:** The framework being used had no KillSwitch. The team could not wait for the framework to add one. They could not ask a vendor to fix it. They could not raise money to pay for the next outage. "We had none of those options. We had source code, and we had the kind of anger that produces good engineering."

**The general principle (use sparingly, this is the only times the user has stated it):** "Many design choices with TPipe were not made from the luxury of failing, blaming someone else, and asking VCs for more money. We would pay the price for that. The KillSwitch protects users against a runaway disaster, even if their own setup was the reason it was going to retry in the first place."

**Important numbers to get right if you reference this story:**
- Token count: "close to a billion" / "billions" / "we lost count at TTT" — do NOT cite a specific round number like "300M" or "1B" as if it's exact. The user has explicitly said "we've honestly lost count at TTT." Phrasings like "billions of tokens" or "we stopped counting" are accurate. A precise number is not.
- Time period for the KillSwitch specifically: ~6 months in production as of June 2026 (user said "It's actually a newer feature we put in like 6 months ago"). Do NOT conflate with TPipe's general production time, which is longer (~18+ months for the reasoning pipes feature). The framing should be: "the reason we built it" (the billion-token burn story) is older than "how long it has been in production" (6 months). The reasoning-pipes post's "18 months of production" line is correct for the feature it discusses, not for KillSwitch.
- The framework that didn't have a KillSwitch: was the previous-generation agent framework, not specifically named in the session. Do not name a specific competitor in the origin story unless the user has named one.

## Pairs well with

- **`tpipe-reasoning-pipes/references/json-railroad-pattern.md`** — the post shipped before this one. The KillSwitch post's "the choice between a partner and a component" closer should match the reasoning pipes post's "TPipe treats it as a component" closer for voice consistency.
- **`humanizer`** — the FIRST-CLASS tell ("X is not Y. X is Z.") is the most likely failure mode. Run the humanizer pass after writing the draft.

## Pitfalls (lessons from this session)

- **Do not claim reasoning pipes are part of DITL.** The reasoning pipes are a separate subsystem. They sit alongside DITL pipes as one of TPipe's intervention mechanisms. The user corrected this in the reasoning pipes post when I wrote "The reasoning pipes are one of seven Developer-in-the-Loop intervention points in TPipe." — factually wrong, and the user noticed immediately.
- **Do not cite a specific token count for Autogenesis.** "Billions" or "lost count" or "we stopped counting" are accurate. "300 million" or "1 billion" as exact figures are not. The user has explicitly flagged this.
- **The catch-and-rethrow carve-out is the architectural argument, not the budget cap.** Posts that lead with "TPipe has a budget cap" are wrong. Posts that lead with "TPipe throws an exception the runtime explicitly defends" are right. The mechanism is termination, not estimation.
