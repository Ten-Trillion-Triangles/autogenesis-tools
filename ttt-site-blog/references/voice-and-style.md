# Voice and style: the bad patterns and how to fix them

This is the inventory of LLM tells Apex has specifically called out. Grep every draft for these before showing the user. Each entry has the pattern, an example from a real draft, and a rewrite that follows Apex's voice.

> **2026-06-06 update:** Two rows in the table below were later flagged by Apex as also being technically wrong (not just voice-wrong). The voice rewrites were correct, but the underlying descriptions of the APIs were wrong:
> - The "Use the typed model enum" row — `setModel` takes ONLY a string, no enum. The constants are `val` on a config object. Full correction in `references/tpipe-api-accuracy.md`.
> - The "Token budgets belong in config" row — `setTokenBudget` is the memory management system, not a cap. Full correction in `references/tpipe-api-accuracy.md`.
>
> The voice rewrites in those rows still work as patterns (positive statements of what to do, not what not to do), but the technical claims they support are wrong. Read `tpipe-api-accuracy.md` before writing any post that touches these APIs.

## Copula avoidance (the big one)

The pattern: describing something as "X, not Y" or "X is not Y" instead of saying what X IS.

### The "X is not Y. X is Z." pattern (FIRST-CLASS tell)

The single most common form this takes in LLM drafts: two consecutive sentences, the first negating something the second asserts. The user calls it "is not X is Y" / "it's not X it's Y." It is the #1 LLM tell this skill must eliminate.

The fix is structural: state what X IS in one sentence. The contrast is implicit. If the reader doesn't get it, that's a sign the contrast was never the point — the positive statement is the point.

**Examples from the 2026-06 reasoning pipes and KillSwitch drafts (all caught and patched):**

| Before | After |
|--------|-------|
| "The LLM is not a conversational partner. The LLM is a left-to-right token predictor." | "The LLM is a left-to-right token predictor. Every token it generates is conditioned on every token before it." |
| "The model is not 'thinking about your prompt.' The model is building a sequence, one token at a time..." | "There is no hidden planner. The model builds a sequence, one token at a time..." |
| "The KillSwitch is not a budget cap. The KillSwitch is termination architecture." | "The KillSwitch is termination architecture. The runtime kills the call chain before the cost accrues." |
| "KillSwitch is not a feature but a termination architecture." | "KillSwitch is termination architecture, not a feature." |
| "The LLM is in the loop as a deterministic emit-and-parse component, not as a colleague you negotiate with." | "You stop negotiating with the model. You wire it up like any other component." |
| "The structured output is observable. The prompt is not." | "The structured output is observable. The prompt is a black box." |
| "The cost and latency savings are not from prompt magic. They are from the schema." | "Those gains come from the schema, not from prompt wording." |
| "The model is not free to write a happy-path plan." | "A happy-path plan is structurally impossible — the schema forces the model to enumerate the risks at every phase." |
| "The choice is not between frameworks. It is between treating the model as a partner you negotiate with and treating it as a component you can wire up." | "The choice is between treating the model as a partner you negotiate with and treating it as a component you wire up." |

**The fix is always the same:** lead with the positive. State what X IS. If a contrast is needed, flip the structure so the positive lands first and the negative becomes a trailing note ("The X is Y, not Z" reads cleaner than "X is not Z. X is Y.").

A single-clause "is not" / "isn't" is fine when the negative is the entire point — "Luck is not a safety system," "This is not a coincidence," "The cost of a false positive is recoverable. The cost of a false negative is not." Don't over-correct. The rule is about the *patterned* "is not X is Y" / "X is not Y. X is Z." structure, not every negative.

### The verb-negation period-separated variant (added 2026-07-21)

The pattern above catches `is not` / `isn't`. The variants `does not`, `did not`, `will not`, `cannot` are structurally identical but the comma-only narrow grep misses them because the period breaks the sentence boundary.

The shape: `X does not Y. X does Z.` or `X did not Y. The subject Y'd.` Two sentences, period between, verb-negation first, positive second. Same AI tell as `is not Y. is Z.`, just with a different verb.

**Examples from the 2026-07-21 "cheapest agent" draft (all caught and patched in the same session):**

| Before | After |
|--------|-------|
| "The engineer did not lose by reaching for the bigger abstraction. The engineer lost by staying at the smaller one past the point where the cognitive load exceeded the cost of the bigger primitive." | "The win was always the bigger abstraction once the system outgrew the engineer's mental model. The loss was staying at the smaller primitive past the point where the cognitive load exceeded the cost of the bigger primitive." |
| "The person does not reach for a PumpStation to send an email, does not reach for a Manifold to summarize a document. The person reaches for the smallest primitive that carries the task, and only escalates when the task itself demands it." | "A person sending an email reaches for an email primitive. A person summarizing a document reaches for a summarize primitive. The person reaches for the smallest primitive that carries the task, and only escalates when the task itself demands it." |
| "The substrate does not impose the discipline. It makes the discipline cheap to follow." | "The substrate makes the discipline cheap to follow." |

**Detection.** When a verb-negation (`does not`, `did not`, `will not`, `cannot`) is followed by a period AND the next sentence opens with the same subject making a positive claim, the verb-negation clause is the banned shape. Rewrite by dropping the verb-negation and stating only the positive.

The "rather than" variant. The pattern `stay with A rather than with B` forces the reader to scan past the negative framing to find the positive. Restate as a single positive sentence: `keep A and pay only for what you wrote.` The "rather than" was visible only after the narrow grep caught it — same session, same post. Grep: `grep -niE "rather than|instead of" src/content/blog/<post>.md`. Each hit: read it. If the second clause carries the point, rewrite as a positive statement.

### Examples from the pipeline blog draft (all patched)

| Before | After |
|--------|-------|
| "No DSL exists for individual pipes, and it shouldn't — a pipe is one component, the builder is the right shape." | "A pipe is one component. The builder is the right shape for a single component." |
| "Misuse is a build error, not a runtime surprise." | "Misuse fails the build. The builder lets it through to runtime." |
| "It's a style choice, not a different pattern." | "It's a style choice. Both compile to the same place." |
| "Use a config value, not a magic number." | "Put token budgets in your config object." |
| "Use the typed model enum, not the string." | "Use the typed model enum." (voice pattern OK; technical claim wrong — see api-accuracy.md) |
| "The scope DSL doesn't help you if you nest it five levels deep." | "Stop nesting the scope DSL five levels deep." |
| "init() is not optional." | "Always call init()." |
| "setTokenBudget is not just a cap." | "setTokenBudget is the memory management switch." |
| "Token budgets belong in config, not in code." | "Token budgets belong in your config object." (voice pattern OK; technical claim wrong — see api-accuracy.md) |
| "The block compiles, but the inferred type is `JunctionBuilder<HasModerator>`, not `Junction`." | "The block compiles, but only partially. The inferred type is `JunctionBuilder<HasModerator>`. You need to reach `JunctionBuilder<Ready>`..." |
| "This is the boundary where free text meets type." | Cut entirely (topic introducer). |
| "This is how you make the LLM return typed data." | "You use these to make the LLM return typed data." |
| "This is the real reason the scope DSL exists." | "The scope DSL makes configuration errors a build-time problem." |
| "It catches configuration mistakes at build time, not at 3am in production." | "The builder treats order as convention. The scope treats order as structure. You find out at 3am with the builder." |
| "you check this flag instead of catching exceptions" | "Check this flag. Don't try/catch — Connector sets the flag, it doesn't throw." |
| "Use the Converse API instead of the legacy InvokeModel API." | "Use the Converse API. Converse is the unified interface for multi-model access." |

### The fix

Say what to do (positive), not what not to do (negative). If you must show a contrast for teaching, lead with the positive:

- "Use the enum. Strings let typos through to runtime."
- "Stop nesting the scope DSL five levels deep."
- "Always call init()."
- "A pipe is one component. The builder is the right shape."

## Topic introducers

The pattern: "This is the X" / "This is how" / "This is what" at the start of a sentence. LLMs love these as transition devices. Cut them.

### Examples (all cut)

- "This is the boundary where free text meets type." → Cut.
- "This is the bridge between the two patterns." → Cut.
- "This is the real reason the scope DSL exists." → Rewrote as positive statement.
- "This is how you make the LLM return typed data." → "You use these to make the LLM return typed data."
- "This is the first/second/third benefit of X." → Cut. State the benefit directly.

### The fix

Just say the thing. Don't label the next sentence. If you can't state the benefit directly, it's not actually a benefit — cut it.

## "Without X" / "Instead of" / "Rather than" / "Skip it"

The pattern: framing an instruction as "without doing X" or "instead of Y" or "skip it for Z" rather than just saying what to do.

### Examples

| Before | After |
|--------|-------|
| "Without this, setJsonOutput doesn't do much." | "Makes setJsonOutput work. Pair them." |
| "Use the Converse API instead of the legacy InvokeModel API." | "Use the Converse API. Converse is the unified interface." |
| "Also enables semantic context splitting instead of truncating from the end." | "Split mode also handles context overflow by summarizing + keeping the most relevant recent content." |
| "Skip it for simple classification." | "For simple classification, the reasoning pipe adds latency — skip it." |
| "Use this for complex generation tasks. Skip it for simple classification." | "Use this for complex generation tasks. For simple classification, the reasoning pipe adds latency — skip it." |
| "Calling execute() on an uninitialized pipe throws." | OK (descriptive of behavior, not a directive) |

### The fix

When the directive is the right thing, lead with it. When describing what a feature does, describe what it DOES, not what it doesn't do.

### The "rather than" prose variant (added 2026-07-21)

Different from the directive-style "rather than" above. The prose variant appears in narrative voice when the author frames a positive claim through a negative contrast — `stay with A rather than with B`, `keep A rather than pay B for nothing`. The reader has to scan past the negative framing to find the positive claim. Same AI tell as the verb-negation variant.

**Example from the 2026-07-21 "cheapest agent" draft:**

| Before | After |
|--------|-------|
| "The statement is about cost, control, and the engineering depth you keep when the routing decisions stay with the engineer rather than with an abstraction that charges for the privilege." | "The statement is about cost, control, and the engineering depth you keep when the routing decisions stay with the engineer and you keep paying only for what you wrote." |

**Detection.** `grep -niE "rather than|instead of" src/content/blog/<post>.md`. The directive-style hits are usually inside instructional prose. The prose-style hit lands inside declarative claims about the architecture. If the second clause carries the point, rewrite as a single positive sentence.

## Counting benefits

The pattern: "This is the first benefit. This is the second benefit. This is the third benefit."

Just cut these. State the benefit directly. If you can't state it directly, it's not actually a benefit.

## "Let me walk you through" / "Let me show you" / "Let me explain"

Cut. Replace with "Here's what X does" or just the code.

### Example

| Before | After |
|--------|-------|
| "Let me walk through what each setting does." | "Here's what each one does." |
| "Let me show you the state machine." | "Here's the state machine." (or just show it) |

## The grep to run on every draft

```bash
# Copula avoidance (the most common LLM tell)
grep -nE "isn't|is not|not the |not a |not just|not only|never |not optional|not X|doesn't|won't|don't |instead of|skip it|Use X not Y|isn't allowed|not required" /path/to/draft.md

# The "X is not Y. X is Z." pattern specifically — first-class tell.
# In practice, scan every "is not" / "isn't" match: if the next sentence asserts what it IS, rewrite to lead with the positive.
# A simple grep that catches the most common shape:
grep -nE "is not|isn't" /path/to/draft.md  # then manually inspect each match's surrounding 2-3 lines

# The verb-negation period-separated variant (added 2026-07-21) — catches "X does not Y. X does Z."
# and "X did not Y. The subject Y'd." which the comma-only narrow grep misses.
python3 -c "
import re
b = open('/path/to/draft.md').read()
for m in re.finditer(r'(\b(?:does not|did not|will not|cannot) \w[\w\s]{0,60})\.\s+(\b(?:does|did|the|it|they|the subject)\b)', b, re.IGNORECASE):
    print(f'{m.start()}: {m.group(1)[:50]}. {m.group(2)[:30]}')"

# "rather than" prose variant — narrative contrast forcing the reader past the negative
grep -nE "rather than|instead of" /path/to/draft.md

# "might not" / "will not" hedging triples — three sentences in a row starting with hedging reads as AI doom-prophecy
grep -nE "might not|may not|could not|would not|will not" /path/to/draft.md

# Topic introducers
grep -nE "This is the |This is how|This is what|This is where|This is why|This means" /path/to/draft.md

# "Without X" / "Rather than" / "Let me"
grep -nE "without this|rather than|Let me|Let us" /path/to/draft.md

# Counting benefits
grep -nE "This is the (first|second|third|fourth)" /path/to/draft.md
```

Each match is a candidate patch. Review the context, then rewrite using the patterns above. Re-grep until clean.

**Also grep for technical accuracy.** If a draft describes a TPipe API, cross-check the claim against the actual function in `TPipe/src/main/kotlin/Pipe/Pipe.kt` (or whichever file). The two corrections from 2026-06-06 (`setModel` is string-only, `setTokenBudget` is the memory management system) are both in `references/tpipe-api-accuracy.md` — read that file before writing any post that touches those APIs.

## Reference example: the full pipeline blog

The 2026-06-06 pipeline post went through 19 patches before it was clean. The full list of bad patterns caught is in the SKILL.md (the "Patches applied" table) and in the table at the top of this file. That post is now the canonical example of the voice.

## Reference example: the Autogenesis WriterAgent

The Autogenesis WriterAgent `writerAgent.kt` is a real production example of the `.apply { }` block pattern with full configuration visible. When in doubt about how a TPipe pipe looks in production, read that file. The "guidePipe," "selectionPipe," and "writingPipe" are all built this way.
