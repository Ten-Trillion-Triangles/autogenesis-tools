---
name: ttt-site-code-snippets
description: "Verify TPipe API accuracy and add syntax highlighting to Kotlin/JavaScript code snippets on ttt-site Astro pages (landing pages, comparison pages, blog posts). Triggers when the user reports a code sample 'isn't accurate', 'doesn't compile', 'isn't real TPipe'; asks to add syntax highlighting; or audits a snippet that appears across multiple pages. The TPipe source lives at /home/cage/Desktop/Workspaces/TPipe/TPipe/ (nested under the workspace root), and Shiki 4.x is bundled in ttt-site node_modules for codeToHtml."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ttt-site, code-snippets, kotlin, tpipe, accuracy, syntax-highlighting, shiki, astro]
    related_skills: [ttt-site-comparison-pages, product-claims-audit, ttt-site-blog]
---

# TPipe Code Snippets on ttt-site

Use this skill when working with TPipe API code samples in ttt-site Astro pages — landing pages (`src/pages/*.astro` like `kotlin-ai-agent-framework.astro`), comparison pages (`src/pages/comparison/*.astro`), or blog posts. Two distinct concerns:

1. **API accuracy** — the snippet compiles and matches real TPipe source
2. **Syntax highlighting** — the rendered HTML has per-token colors, not plain text

## When this fires

- User reports a code sample "isn't accurate" / "doesn't compile" / "isn't real TPipe"
- User asks to add syntax highlighting to a `<pre>` block
- User asks to add a new code listing to a landing/comparison/blog page
- Audit sweep: same BedrockPipe snippet appears on 6+ landing pages; user reports inaccuracy on one, sweep the others
- A new TPipe version ships and the install-modal copy / pricing-card copy must bump in lockstep — see PITFALL below
- A landing or install page shows a `setRole()`, `setPipeRole()`, `setTimeout()`, `setPipeTimeout()` (or similar) called as the last link in a fluent chain and the operator wants to know why the consumer-side build fails — see PITFALL below

## API accuracy workflow

### Step 1: TPipe source path is nested

The TPipe source is at `/home/cage/Desktop/Workspaces/TPipe/TPipe/`, NOT at the workspace root. The root contains unrelated files (`analyze_har.py`, `foundation_models.json`, model-name analysis scripts). Always `cd TPipe/` first.

```bash
cd /home/cage/Desktop/Workspaces/TPipe/TPipe
```

### Step 2: Skip build artifacts and worktrees

When grepping for symbols, exclude noise paths:

```bash
find . -type f -name "*.kt" \
  -not -path "*/build/*" \
  -not -path "*/.worktrees/*" \
  -not -path "*/.claude/*" \
  -not -path "*/.gradle/*" \
  -not -path "*/.kotlin/*" \
  -not -path "*/out/*"
```

`TPipe/.worktrees/` contains older branch copies with potentially outdated code. Skip them.

### Step 3: Verify each API call against source

For each method/class/enum in the snippet, grep the source for the declaration:

```bash
# Function signatures in the parent Pipe class
grep -n "fun setModel\|fun setRegion\|fun setSystemPrompt\|fun setReasoningPipe\|fun setTokenBudget\|fun setPageKey\|fun generateText\|open suspend fun init" \
  src/main/kotlin/Pipe/Pipe.kt

# Data class / enum / object declarations
grep -n "^data class\|^class\|^enum class\|^object\|^abstract class" \
  src/main/kotlin/Pipe/Pipe.kt src/main/kotlin/Structs/*.kt
```

Cross-check the package path against the `package ...` line at the top of each file. Cross-check the signature exactly — invented convenience methods are the most common failure mode.

### Step 4: Find the canonical usage example

`TPipe/docs/` contains real-world usage patterns and is the source of truth:

- `docs/core-concepts/reasoning-pipes.md` — Chain-of-Draft setup, `ReasoningSettings`, `reasonWithBedrock(...)`
- `docs/getting-started/first-steps.md` — first pipe setup
- `docs/api/pipe.md` — Pipe API reference
- `docs/bedrock/` — Bedrock-specific patterns

### Step 5: Build the corrected snippet

Use the canonical pattern (see `templates/canonical-bedrock-snippet.kt` for the full file). The BedrockPipe-with-ContextBank case covers most landing pages. For Manifold / DistributionGrid / ContextBank-singleton / JSON-output variants, see `references/verified-snippet-variants.md` — each variant in that file has been verified against the TPipe source.

Key invariants across every variant:
- `useConverseApi()` must be called after `setRegion(...)` to use the unified Converse API (recommended over legacy Invoke API for Claude 3/4 and GPT-OSS)
- `setReasoningPipe(reasoningPipe)` takes a `Pipe`, not an enum. Build the reasoning pipe via `reasonWithBedrock(config, settings, pipeSettings)` first; cast to `BedrockPipe` if you need that type
- `init()` is `open suspend fun` on Pipe (Pipe.kt:4792) — must run inside a coroutine (`runBlocking { ... }`). Without it, `generateText()` throws because the Bedrock client is only constructed in `init()`
- `setPageKey(key)` on each pipe attaches it to a ContextBank page; pair with `pullGlobalContext()` for cross-pipe shared memory
- The Bedrock client is only constructed in `init()`, so the pipe WILL throw at runtime if `init()` is skipped

Canonical BedrockPipe + Chain-of-Draft + ContextBank pattern:

```kotlin
import bedrockPipe.BedrockPipe
import com.TTT.Pipe.TokenBudgetSettings
import com.TTT.Structs.PipeSettings
import Defaults.BedrockConfiguration
import Defaults.reasoning.ReasoningBuilder.reasonWithBedrock
import Defaults.reasoning.ReasoningDepth
import Defaults.reasoning.ReasoningDuration
import Defaults.reasoning.ReasoningInjector
import Defaults.reasoning.ReasoningMethod
import Defaults.reasoning.ReasoningSettings
import kotlinx.coroutines.runBlocking

val bedrockConfig = BedrockConfiguration(
    region = "us-west-2",
    model = "anthropic.claude-3-haiku-20240307-v1:0"
)

val pipeSettings = PipeSettings(
    temperature = 0.2,
    topP = 0.9,
    maxTokens = 1024
)

val reasoningPipe = reasonWithBedrock(
    bedrockConfig,
    ReasoningSettings(
        reasoningMethod = ReasoningMethod.ChainOfDraft,
        depth = ReasoningDepth.Med,
        duration = ReasoningDuration.Short,
        reasoningInjector = ReasoningInjector.SystemPrompt
    ),
    pipeSettings
) as BedrockPipe

val analyzer = BedrockPipe().apply {
    setModel(bedrockConfig.model)
    setRegion(bedrockConfig.region)
    useConverseApi()                          // unified Converse API; recommended
    setSystemPrompt("You are a Kotlin code reviewer. Be terse, specific.")
    setReasoningPipe(reasoningPipe)
    setTokenBudget(TokenBudgetSettings(
        contextWindowSize = 4096,
        maxTokens = 1024,
        reasoningBudget = 256
    ))
    setPageKey("kotlin-review-queue")
}

runBlocking {
    analyzer.init()                           // constructs the Bedrock client (suspend)
    val result = analyzer.generateText("Review:\n$code")
    println(result)
}
```

### Step 6: Sweep sibling pages

The same BedrockPipe snippet appears on 6+ landing pages. When fixing one, audit the others:

```bash
bash /home/cage/.hermes/skills/software-development/ttt-site-code-snippets/scripts/sweep-broken-bedrock-snippet.sh
```

Known affected pages (as of June 2026):
- `src/pages/kotlin-ai-agent-framework.astro` (fixed)
- `src/pages/long-horizon-ai-agents.astro`
- `src/pages/deterministic-ai-agents.astro`
- `src/pages/agent-operating-environment.astro`
- `src/pages/ai-agent-orchestration-kotlin.astro`
- `src/pages/persistent-memory-ai-agents.astro`

## Syntax highlighting with Shiki

The site uses `<pre class="code-block"><code>...</code></pre>` blocks with no per-token color. Shiki 4.x is bundled in `node_modules` and works inside `.astro` frontmatter via `codeToHtml`.

### Step 1: Import and call in frontmatter

```astro
---
import { codeToHtml } from 'shiki';

const kotlinSample = `package com.example
fun greet(name: String) = "Hello, $name"
`;

const highlightedHtml = await codeToHtml(kotlinSample, {
    lang: 'kotlin',
    theme: 'github-dark'
});
---
```

### Step 2: Render in the template

```astro
<div class="code-block shiki-container" set:html={highlightedHtml} />
```

Shiki emits `<pre class="shiki github-dark"><code>...<span style="color: #xxx">token</span>...</code></pre>`. The outer `<pre>` carries the dark-theme background; the inner `<code>` carries the tokens.

### Step 3: CSS adjustments

The page's existing `.code-block` rule sets background/padding/border-radius. The shiki wrapper emits its own `<pre>` inside, so the styles need to compose:

```css
.code-block { background: var(--color-surface-container); padding: 1.25rem; border-radius: 0.5rem; overflow-x: auto; font-size: 0.85rem; line-height: 1.5; color: var(--color-on-surface); margin: 1rem 0; }
.code-block code { font-family: 'JetBrains Mono', 'Fira Code', monospace; white-space: pre; }
.code-block.shiki-container { padding: 0; }
.code-block.shiki-container pre.shiki { background: transparent; padding: 1.25rem; margin: 0; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.85rem; line-height: 1.5; }
```

The `.shiki-container` overrides outer padding to 0 so the inner `<pre>` owns the padding. The inner `.shiki` background is transparent so the page's `.code-block` background shows through.

### Step 4: Verify build + visual

```bash
npm run build  # must be clean — Shiki runs at build time
```

Then visually verify per-page via Playwright. Build-time errors surface as `codeToHtml` failures on the first affected page.

## Pitfalls

- **The TPipe workspace root is NOT the source root.** `/home/cage/Desktop/Workspaces/TPipe/` contains analysis scripts and model-name files — go to `/home/cage/Desktop/Workspaces/TPipe/TPipe/`. This is already noted in `ttt-site-comparison-pages` as a pitfall but easy to miss on a fresh task; check both skills if a TPipe symbol grep returns empty.

- **Invented methods are the most common failure mode.** Marketing snippets invent convenience methods that look reasonable but don't exist. Real examples from June 2026, all confirmed absent from `/home/cage/Desktop/Workspaces/TPipe/TPipe/` source:
  - `attachContextBank(pageKey = "...")` — real API is `setPageKey(key: String)` on Pipe.kt
  - `setReasoningPipe(ChainOfDraft)` (passing enum) — real is `setReasoningPipe(pipe: Pipe)` after building via `reasonWithBedrock(config, settings, pipeSettings)`
  - `JsonOutput(schemaString)` wrapper — no such class; `setJsonOutput(json: String)` takes the raw JSON schema directly
  - `ContextBank.connect(pageKey, lorebook)` — no such method; `ContextBank` is an `object` singleton with `emplaceWithMutex(key, ContextWindow)` and `getContextFromBank(key)`
  - `Manifold(manager = ..., workers = listOf(...))` — no such constructor; real is `Manifold().setManagerPipeline(pipeline)` + `addWorkerPipeline(pipeline)` per worker
  - `manifold.cycle(query, pausePoints, onPause)` — no such method; real surface is `manifold.execute(MultimodalContent)` + `manifold.pause()` / `manifold.resume()`, with declarative pause points on the inner Pipeline (`pauseBeforePipes()`, `pauseAfterPipes()`, `pauseOnCompletion()`)
  - `registerP2P(nodeId = "...")` — no such method on Pipe; P2P registration lives on the DistributionGrid as `addPeer(...)` + `registerWithRegistry()`
  - `contentOf("string")` — invented helper; `MultimodalContent(text: String)` is a real constructor in `com.TTT.Pipe.MultimodalContent`

  Always grep the source for the exact method name before trusting it.

- **`init()` is required before `generateText()`.** The Bedrock client is only constructed inside `init()` (Pipe.kt:4792), and `init()` is `open suspend fun` — must run inside a coroutine (`runBlocking { ... }`). A snippet that builds the pipe and calls `generateText(...)` without `init()` compiles fine but throws at runtime. Include `init()` in any "complete working example."

- **`useConverseApi()` should be set after `setRegion(...)`.** BedrockPipe has two API paths — the legacy `Invoke` API and the newer `Converse` API (Pipe.kt:354). Converse is the recommended path for Claude 3/4 and GPT-OSS, gives unified request handling across model families, and supports streaming via ConverseStream. If a snippet calls `setRegion` without `useConverseApi()`, it falls back to legacy Invoke, which has model-specific JSON format quirks and weaker streaming support.

- **`setReasoningPipe(pipe: Pipe)` takes a Pipe, not an enum value.** Signature in Pipe.kt:4254. The reasoning pipe must be built first via `reasonWithBedrock(bedrockConfig, reasoningSettings, pipeSettings)` (or `reasonWithOllama(...)`) and then passed in. Passing an enum like `ReasoningMethod.ChainOfDraft` directly does not compile. The cast `as BedrockPipe` is a normal Kotlin downcast — `reasonWithBedrock` returns `Pipe`, and most snippets want the concrete `BedrockPipe` handle.

- **Package paths can be lowercase.** `bedrockPipe.BedrockPipe` (not `com.tpipe.bedrock.BedrockPipe`). Cross-check the actual `package ...` declaration at the top of each source file — don't guess from the directory structure.

- **`ContextBank` is an `object` singleton, not a class.** Imported as `import com.TTT.Context.ContextBank`. You never instantiate it; you call `ContextBank.emplaceWithMutex(...)` and `ContextBank.getContextFromBank(...)` directly. The only `connect(...)`-style method is `connectToRemoteMemory(url, token, useGlobally)` for MemoryServer.

- **`Manifold` has no `(manager, workers)` constructor.** Real builder: `Manifold().setManagerPipeline(managerPipeline)` + `addWorkerPipeline(workerPipeline)` per worker. Each worker must be wrapped in a Pipeline (even if it's a single-pipe pipeline). Pause points are configured via Pipeline methods (`pauseBeforePipes`, `pauseAfterPipes`, `pauseOnCompletion`, `pauseWhen { pipe, content -> ... }`).

- **`DistributionGrid` exposes `addPeer(...)` + `registerWithRegistry()`, not `registerP2P(...)`.** The DSL entry point is `distributionGrid { router(pipeline) ... }` from `com.TTT.Pipeline.distributionGrid`. Init via `grid.init()` (suspend). Registry bootstrap via `grid.registerWithRegistry()` (suspend).

- **Astro interprets `{...}` as a template expression in frontmatter.** When writing a snippet in a backtick-delimited template literal that needs literal curly braces (e.g., `"$variable"` interpolation), escape with `\${...}` so Astro doesn't try to evaluate it. Inside the source string itself, normal Kotlin interpolation is fine — the escape is only needed if the snippet uses JS template-syntax that conflicts with Astro's frontmatter parser. Same applies to `${variable}` references inside the Kotlin code shown to readers — Astro will choke on `${state.checkpoint}` unless escaped.

- **Shiki runs at build time.** If a Kotlin language file fails to load (rare — kotlin is bundled in Shiki's default language bundle), the entire page build fails. The fix is to verify the language is in the bundled set before calling `codeToHtml`.

- **Use `github-dark` theme to match site palette.** The page CSS uses `var(--color-surface-container)` (dark gray ~#2a2a2a) for the `.code-block` background. `github-dark` provides the best contrast on that background — lighter themes (github-light, min-light) will have poor token contrast.

- **Run `npm run build` after edits, not just the dev server.** Astro dev server caches `<style>` blocks via Vite HMR; a CSS change can pass visual review in the browser but fail to ship if HMR was stale. `npm run build` exercises the production path that ships to Amplify and is the real verification. Then `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4321/<page>/` to confirm the dev server still serves it.

## See also

- `templates/canonical-bedrock-snippet.kt` — verified working BedrockPipe + Chain-of-Draft + ContextBank pattern, ready to drop into a snippet block
- `references/verified-snippet-variants.md` — verified source-checked patterns for Manifold (manager-worker + pause/resume), DistributionGrid (multi-node P2P), ContextBank singleton reads/writes, and JSON output determinism. Each variant has been confirmed against `/home/cage/Desktop/Workspaces/TPipe/TPipe/` source. Reach for these when the page narrative calls for a non-default TPipe feature.
- `scripts/sweep-broken-bedrock-snippet.sh` — static audit script that finds pages with invented APIs. Updated June 25, 2026 to cover 14 patterns including Manifold/cycle/P2P/ContextBank.connect variants discovered in the 6-page sweep. Run before declaring a fix complete.
- Related skills: `ttt-site-comparison-pages` (voice rules apply to all ttt-site marketing copy), `product-claims-audit` (broader marketing-claim verification)

## Pitfalls — install-link version bumping and TPipe fluent setter discrimination

**The ttt-site install-link version string lives in TWO files; bump both, or the install modal will advertise a stale version after the next publish.** The pricing component carries the published version in two sources of truth:

- `src/components/pricing/TierCards.astro` — module-scope `const PIPE_COMMAND` / `const PIPELINE_COMMAND` strings (lines 6-7) for the two tier card buttons. These flow through `data-install-command={PIPE_COMMAND}` on the `Get Started` buttons into `InstallModal`'s `commandText.textContent = command`.
- `src/components/pricing/InstallModal.astro` — Props-default fallbacks for `pipeCommand` / `pipelineCommand` (lines 10-11) for pages that render `<InstallModal />` WITHOUT passing the Props explicitly (i.e., any page that uses the modal as a generic install widget).

Both must be bumped together when a new TPipe version ships. Bumping only `TierCards.astro` leaves the modal's copy-to-clipboard default at the old version (silent regression — the buttons show new, the modal hands out old). Bumping only `InstallModal.astro` with no parent override leaves the buttons at the old version. Verified class-level check after any bump:

```bash
grep -nE 'TPipe:[0-9]' src/components/pricing/TierCards.astro src/components/pricing/InstallModal.astro
# Every hit must be on the target version (e.g., 1.0.15), no prior-version stragglers.
```

The PublishPoint URL constants on lines 12-13 (`PIPE_PUBLISHPOINT_URL` / `PIPELINE_PUBLISHPOINT_URL`) do NOT change between publishes — only the version string on lines 6-7 (and the InstallModal Props defaults on lines 10-11) do. Captured 2026-08-04 on the TPipe 1.0.15 publish.

**On TPipe, some `set*` setters are fluent (return `Pipe`) and some are void (return `void`). Marketing snippets that chain all setters end-to-end break compile when a void setter lands in the chain.** Verified on TPipe 1.0.15 bytecode (`javap -classpath TPipe-1.0.15.jar -public com.TTT.Pipe.Pipe`): the fluent-vs-void split is property-driven — Kotlin `var` properties with a custom setter that returns `this` show up as fluent; setters on normal `val` fields or setters declared as `void setX(...)` show up as `void`.

Known void setters on `Pipe` (TPipe 1.0.15, will shift as the API evolves — always re-verify with `javap` against the published jar before writing a snippet):

- `setPipeRole(PipeRole)` — `public final void setPipeRole(com.TTT.Enums.PipeRole)` in the bytecode view.
- `setPipeTimeout(long)`, `setEnablePipeTimeout(boolean)`, `setApplyTimeoutRecursively(boolean)`.
- `setKillSwitch(KillSwitch)`.

Known fluent setters (return `Pipe`): `setPipeName`, `setStreamingEnabled` (also has a void overload from the interface — use the chainable property-setter path), `setModel`, `setSystemPrompt`, `setMiddlePrompt`, `setUserPrompt`, `setTemperature`, `setTopP`, `setMaxTokens`, `setContextWindowSize`, `setProvider`, `setFooterPrompt`, `setJsonInput(String)`, `setJsonOutput(String)`, etc.

A safe pattern for any ttt-site landing-page snippet that needs every setter inside a chain:

```kotlin
val pipe: Pipe = DummyPipe()
    .setPipeName("...")
    .setStreamingEnabled(true)
    .setModel("...")
    .setSystemPrompt("...")
val pipeWithRole = pipe  // no fluent setPipeRole — assign to val and drop
```

Or for the rationale-heavy version: `val dummy = DummyPipe().setModel("...")` and call `dummy.setPipeRole(PipeRole.Other)` as a statement on the intermediate `dummy` before assigning to the publishable `Pipe` handle. The read-time rule: **probe the API surface with `javap -classpath <published-jar> -public com.TTT.Pipe.Pipe | grep 'public.*set[A-Z]'`** before writing any consumer-side snippet that chains more than three setters. Captured 2026-08-04 on the TPipe 1.0.15 fresh consumer bootstrap.

Related pattern (`Pipe` is abstract; `DummyPipe()` is the no-arg concrete entrypoint): see `tpipe-pipe-internals` for the abstract-vs-concrete rule and the `DummyPipe` usage. When wiring a marketing snippet, the contract is:

```kotlin
import com.TTT.Pipe.DummyPipe
import com.TTT.Pipe.Pipe

val pipe: Pipe = DummyPipe()
    .setModel("anthropic.claude-3-haiku-20240307-v1:0")
    .setSystemPrompt("...")
    .setStreamingEnabled(true)
// pipe.setPipeRole(PipeRole.Other)  ← must be a statement, not chained
```

If a snippet on a landing page needs `setPipeRole` to drive role-based behavior, the correct render is a two-stage construction (fluent chain first, then the void setter as a statement). `Pipe::class.qualifiedName` references in the page copy are still valid; what fails is the chained call.