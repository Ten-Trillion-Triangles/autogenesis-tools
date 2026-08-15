# Source locations for TPipe blog content

When writing a TPipe blog post, pull real code from these locations rather than inventing it. The Autogenesis WriterAgent is the canonical reference; the TPipe docs are the secondary reference.

## Production code: Autogenesis WriterAgent (canonical reference)

The Autogenesis game server is the most-used source for TPipe blog examples. It's a KMP game server + browser UI running on TPipe. The WriterAgent is a 3-pipe guide/selection/writing system that runs for 100+ turn TTRPG sessions.

```
/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/
├── writingAgent/
│   ├── writerAgent.kt           # guidePipe, selectionPipe, writingPipe — all `.apply { }` blocks
│   └── ResponseRefinementAgent.kt
├── judgeOutcome/
│   ├── judge.kt
│   ├── npcJudge.kt
│   └── geoPoliticsAssessmentAgent.kt
├── playerAgent/
│   └── playerAgent.kt
├── validateAction/              # action validation agents
├── gatherContext/               # context-gathering agents
├── lorebook/                    # LoreBook management agents
├── modifyGameState/             # game-state mutation agents
├── passFailAgent/               # pass/fail classification agents
└── systemActions/               # system-level action agents
```

`writerAgent.kt` is the gold standard. It has all three pipes built with `.apply { }` blocks with full configuration visible. Use it for any blog post about:
- Pipeline construction (the `.apply { }` block pattern)
- JSON output typing (`setJsonInput` / `setJsonOutput`)
- Reasoning pipes (`setReasoningPipe` + `authorBuilder`)
- LoreBook memory injection (`enableLoreBookFillAndSplitMode`)
- Token budgets (`setTokenBudget`)
- Guardrails / conditional system prompts

### LorebookAgent (canonical reference for memory agents)

The LorebookAgent at `Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/lorebook/lorebookAgent.kt` is the second canonical reference after the WriterAgent. It is the production implementation of a memory agent — a pipe that reads from the ContextBank, runs an LLM extraction step over the recent context, and writes structured lorebook entries back to the bank.

The pattern (lines 166-280 in the current source) is the spine of any "memory agent" blog post:
1. Read the bank-held window by key: `ContextBank.getContextFromBank("story")`
2. Loop over extracted entity categories (characters, events, locations, items, factions, relationships)
3. For each entity, call `addLoreBookEntry` (new) or `combineValue` (merge into existing)
4. Write the merged window back: `ContextBank.emplaceWithMutex("story", storyContext)`

This is the full read-extract-write loop. The two-pipeline composition with the WriterAgent — one pipeline writes raw prose to `contextElements`, the other pipeline reads it and updates `loreBookKeys` — is the entire memory agent architecture. Any post about memory agents / lorebook maintenance / "lorebook that writes itself" patterns should pull code from this file.

### How to read writerAgent.kt

Each pipe is structured the same way:
1. Pipe instantiation with `.apply { }`
2. Configuration calls in a logical order: API → region → model → sampling → typing → budget → reasoning → naming → memory → prompts
3. `init()` called separately (in Autogenesis's case, after all pipes are built in a separate pass)

When you pull code from writerAgent.kt for a blog post, the natural truncation is the first 15-20 lines of the `.apply { }` block — that's where the most universally-applicable settings are (API selection, region, model, temperature, top-p, JSON input/output, token budget).

## TPipe framework source (for DSL/container examples)

The TPipe framework itself is the source for scope DSL examples. The docs are at:

```
/home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
├── getting-started/
│   ├── installation-and-setup.md
│   └── first-steps.md                      # Hello world with TPipe
├── core-concepts/
│   ├── pipeline-class.md                   # Pipeline builder pattern
│   ├── killswitch.md                       # Has `manifold { }` and `junction { }` DSL examples
│   ├── why-tpipe.md                        # The architectural rationale
│   └── streaming-callbacks.md
├── containers/
│   ├── manifold.md                         # Full DSL block reference
│   ├── junction.md                         # State machine documentation (Initial → HasModerator → HasParticipants → Ready)
│   ├── distributiongrid.md                 # DSL builder section
│   ├── connector.md                        # Builder pattern
│   ├── splitter.md                         # Builder pattern
│   ├── multiconnector.md
│   ├── pumpstation.md
│   └── cross-cutting-topics.md             # DITL hooks, lifecycle handling
├── comparison/
│   └── TPipe-vs-Apache-Camel-Comparison.md # Has `manifold {}`, `junction {}`, `pumpStation {}` examples
├── case-studies/
│   ├── headless-use-cases.md
│   └── grounded-case-studies.md
├── advanced-concepts/
│   ├── remote-memory.md                    # Multi-region pipe configuration examples
│   ├── p2p.md
│   └── trace-server.md
├── api/
│   ├── tpipe-defaults-package.md
│   └── ...
├── bedrock/
│   ├── getting-started.md
│   └── ...
├── openrouter/
│   └── getting-started.md                  # Canonical "what each setting does" reference
├── ollama/
│   └── getting-started.md
└── ...
```

### Grep commands for finding examples

```bash
# Find DSL examples
grep -rn "manifold {" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
grep -rn "junction {" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
grep -rn "distributionGrid {" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
grep -rn "pumpStation {" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
grep -rn "pipeline {" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/

# Find pipe construction examples
grep -rn "BedrockMultimodalPipe" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
grep -rn "OpenRouterPipe" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/
grep -rn "BedrockPipe()" /home/cage/Desktop/Workspaces/TPipe/TPipe/docs/

# Find Autogenesis pipe construction (the canonical `.apply { }` style)
grep -rn "BedrockMultimodalPipe().apply" /home/cage/Desktop/Workspaces/Autogenesis/
```

The `openrouter/getting-started.md` file is the best reference for "what each setting does" — it walks through OpenRouterPipe options one by one. The `killSwitch.md` and `containers/junction.md` files are the best for scope DSL examples.

## The blog directory

```
/home/cage/Desktop/Workspaces/ttt-site/
├── src/
│   ├── content/blog/                       # Where new posts go
│   ├── content.config.ts                   # Frontmatter schema (read this first)
│   ├── pages/
│   ├── components/
│   └── ...
├── public/
├── amplify.yml                             # CI/CD - clones TPipe/docs during build
└── ...
```

The dev server is `astro dev` running on port 4321. Hot-reload picks up new content collection entries automatically. New posts are accessible at `/blog/YYYY-MM-DD-slug/`.

To verify a new post is live:
```bash
curl -s -o /dev/null -w "post: %{http_code}\n" http://127.0.0.1:4321/blog/YYYY-MM-DD-slug/
```

## Existing TPipe blog posts (for style reference)

```
/home/cage/Desktop/Workspaces/ttt-site/src/content/blog/
├── 2026-04-26-introducing-tpipe-agent-operating-substrate.md
├── 2026-04-27-agent-substrate-what-why-how.md
├── 2026-04-27-llm-fundamentals-what-they-are.md
├── 2026-04-28-tpipe-memory-what-why-how.md
├── 2026-05-04-headless-agents-what-why-how.md
├── 2026-05-11-p2p-agent-communication-inevitable.md
├── 2026-05-12-you-cannot-build-agent-substrate-in-python.md
└── 2026-06-06-how-to-build-a-tpipe-pipeline.md  # the canonical tutorial-style post
```

Style reference ranking (best to weakest for matching Apex's voice):
1. **2026-06-06-how-to-build-a-tpipe-pipeline.md** — the tutorial-style post. Best match for "how to" voice. Most patches applied during writing.
2. **2026-05-12-you-cannot-build-agent-substrate-in-python.md** — closer to opinion/manifesto, but well-structured. Good for thought-leadership posts.
3. **2026-04-28-tpipe-memory-what-why-how.md** — good tutorial structure, but uses some "X is not Y" patterns that should be cleaned up if revised.

The LLM-fundamentals post (2026-04-27-llm-fundamentals-what-they-are.md) is intentionally accessible to a non-technical audience — different voice, not a reference for tutorial posts.
