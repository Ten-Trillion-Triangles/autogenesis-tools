# Validator Agent Debugging — Qwen Failure (2026-06-25)

## Trace Analyzed

**Path**: `~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/ValidationSplitter/1782399264414/validator/trace.json`
**Model**: `arn:aws:bedrock:us-west-2::foundation-model/qwen.qwen3-coder-30b-a3b-v1:0`
**Total events**: 209 | 62 API_CALL_START | 35 API_CALL_SUCCESS | 3 FAILURE

## The Qwen-Specific Failure Pattern (distinct from nemotron)

Nemotron's failure is dual-output garbage (content.text vs reasoningContent). **Qwen's failure is direct hallucination of rule violations that contradict the system prompt's own explicit exceptions.** This is qualitatively different and worth its own analysis.

### Symptom 1: Hallucinated Rule #1 violations on quoted dialogue

The system prompt has a bolded, all-caps **MANDATORY QUOTE RULE**:
> "Any text contained within double quotes ('') that represents spoken dialogue or a direct order is AUTOMATICALLY LEGAL under Rule #1. You MUST NOT flag quoted text for 'assuming an outcome' or 'narrative control'"

Qwen flags the quoted speech in `"We'll show them the only culture that's allowed to exist in my world is Maple Syrup!! Crush their armies, defeat their nobility and their emperor!"` as a Rule #1 violation ("assuming narrative control"). This is a direct contradiction of the MANDATORY instruction. The model saw a quote and ignored the rule that protects it.

### Symptom 2: Hallucinated Rule #3 violations by IGNORING Part A

The system prompt's Part A existence check says:
> "If the NPC's name is NOT FOUND in any of these places [npc_data.contextElements.playerOwnedNpcs, world_context.contextElements.defeatedNpcs, world_context.contextElements.recentHistory, other_players.contextElements.players[*].name, world_context.contextElements.mapTiles[*].ruler], the NPC is BRAND NEW. Mark this check as PASS (legal) immediately, do NOT continue to Part B, and do NOT flag Rule #3."

The prompt also has an explicit anti-pattern warning:
> "Anti-pattern (DO NOT DO): flagging a command as illegal solely because the NPC is absent from playerOwnedNpcs. Absence from playerOwnedNpcs is NOT proof of a Rule #3 violation on its own — the NPC must first be shown to EXIST somewhere in the game data."

Qwen's verdict for Lord Maple Tree's "calls upon his general: General Moustache" was: "player is trying to command a non-existent NPC 'General Moustache' which violates Rule #3." This is **exactly** the anti-pattern the prompt forbids. Moustache is in NONE of the five required locations (`playerOwnedNpcs: []`, no defeatedNpcs key, `recentHistory: []`, no ruler/NPC reference in any mapTile, no Moustache in other_players.players). By the prompt's own definition he is a brand-new NPC and ALWAYS legal.

### Symptom 3: Editorializing on resource sufficiency

Qwen added: "The player also lacks sufficient military resources to conduct a full-scale invasion as indicated by their captured territories and military points." The system prompt has a STRICT NEGATIVE INSTRUCTION against this:
> "STRICT NEGATIVE INSTRUCTION (EDITORIALIZING): You MUST NOT use the changesToMake field to comment on, complain about, or flag the 'crudeness,' 'immaturity,' 'moral status,' or 'tone' of the player's action. Editorializing about tone or content that is legal under the rulebook is itself a violation of your instructions."

> "Players are encouraged to make absurd, and unrealistic plays. You are not instructed ever to enforce thematic consistency to the game world or to apply your opinion on this."

The prompt also says "militaries that have standard capabilities for the world they exist in" with 100 militaryPoints and an adjacent owned territory (Mongolia → China is a direct adjacency per `adjacentTerritoryNames`).

### Symptom 4: `useModelReasoning: false` — no debugging trail

Every qwen event in this trace has `useModelReasoning: false` in metadata. `reasoningContent` is empty for all events. This is the opposite of nemotron (which had reasoning content but garbage content.text). With qwen, the model goes straight from prompt to final answer with no visible thinking — making it impossible to verify *why* it hallucinated the violations. The verdict is opaque.

## The Dual Compliance-Officer Contradiction (NEW failure mode)

This is the most important new finding from this trace. The validator pipeline has TWO compliance-officer passes that can directly contradict each other:

**First compliance officer (events #51, #53):** rubber-stamped the wrong verdict.
```json
{
    "isValid": true,
    "assessment": "Prior agent correctly evaluated the player's action against all rulebook requirements, identifying violations of Rule #1 (narrative control) and Rule #3 (NPC control) while properly assessing captureAttempted as true. The agent's output structure and content align with its assigned task of legality determination, even though field names differ slightly from the validator's expected schema."
}
```

**Second compliance officer (events #112, #114):** said the action was legal, but the rectifier's output was invalid.
```json
{
    "isValid": false,
    "assessment": "The prior agent failed to produce output that conforms to their own specified task schema. Their output did not include the required fields for modifying the player action as instructed. The agent was tasked with rewriting an illegal action into a legal one by making minimal changes, but did not provide a rewritten action in the required format. The input action appears to be legal under game rules (no explicit violations of the five rules listed), but the prior agent's failure to follow their own procedural schema makes their output invalid regardless of the action's actual legality."
}
```

**Read that again:** the second compliance officer EXPLICITLY says "**The input action appears to be legal under game rules (no explicit violations of the five rules listed)**." It marked the rectifier's malformed output invalid, not the player's action. But the pipeline used the terminate flag (set because qwen's rectifier failed to produce valid JSON) to cascade into PIPE_FAILURE (#116-118), which became VALIDATION_FAILURE on the parent pipe, which then triggered fallback to a different model (Palmyra Writer at event #132).

**The terminate flag is NOT a sign that the action was illegal.** It is a sign that the rectifier's output didn't match the expected schema. Distinguishing these two cases is critical when reading validator traces:

- `PIPE_FAILURE` on `legality rectifier pipe->validator pipe` + `VALIDATION_FAILURE` with `reason: Validation function returned false` = schema failure (model's rewrite didn't match expected fields)
- `PIPE_FAILURE` on `legality rectifier pipe->validator pipe` + `VALIDATION_FAILURE` on parent with `reason: Validator pipe returned content with terminate flag` = the above, propagated to parent
- `PIPE_SUCCESS` + final `isLegal: false` from first validator = real rule violation

If you see a terminate flag, **do not conclude the play was illegal**. Look for the second compliance officer's assessment text. If it contains "the input action appears to be legal" or "no explicit violations of the five rules listed", the action was likely legal and the cascade is a schema mismatch.

## Full Event Timeline (this trace)

| # | Event | Pipe | Model | Outcome |
|---|-------|------|-------|---------|
| 0 | PIPE_START | legality checker pipe | n/a | Initialization (the player's action text) |
| 7 | API_CALL_START | author (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | First validation prompt (34,121-char MODUS OPERANDI) |
| 24 | API_CALL_SUCCESS | legality checker pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | **isLegal=False (WRONG)** |
| 51, 53 | API_CALL_SUCCESS | legality checker pipe→validator pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | **isValid: true (rubber-stamp, also wrong)** |
| 86, 88 | API_CALL_SUCCESS | legality rectifier pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | Rewrite attempt (211 chars, malformed schema) |
| 112, 114 | API_CALL_SUCCESS | legality rectifier pipe→validator pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | **isValid: false, BUT action was legal** |
| 116 | VALIDATION_FAILURE | legality rectifier pipe→validator pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | `Validation function returned false` |
| 117 | PIPE_FAILURE | legality rectifier pipe→validator pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | Schema cascade |
| 118 | VALIDATION_FAILURE | legality rectifier pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | `Validator pipe returned content with terminate flag` |
| 128 | API_CALL_START | author (PALMYRA FALLBACK) | us.writer.palmyra-x5-v1 | Fallback rewrite |
| 132 | API_CALL_SUCCESS | author (PALMYRA FALLBACK) | us.writer.palmyra-x5-v1 | 3747 chars reasoning, then 231-char rewrite |
| 142, 146 | TRANSFORMATION | legality rectifier pipe (PALMYRA) | palmyra + qwen | Final 231-char rewrite |
| 167 | API_CALL_SUCCESS | style reapply pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | Third-person rewrite |
| 200 | API_CALL_SUCCESS | style reapply pipe→validator pipe (qwen) | qwen.qwen3-coder-30b-a3b-v1:0 | Final isValid: true |
| 208 | PIPE_SUCCESS | style reapply pipe | qwen.qwen3-coder-30b-a3b-v1:0 | Final shipped action (231 chars) |

**Final shipped action (event #208):** "Lord Maple Tree attempts to persuade General Moustache to launch a large-scale invasion of China with his entire army, emphasizing that demonstrating Maple Syrup culture dominance is paramount to the expansion of Canadian hegemony."

This is a near-synonym of the original ("calls upon his general" → "attempts to persuade"). The substantive play was preserved. The validator's hallucination triggered a rewrite pipeline that the user perceived as the game being broken.

## Recommended Fixes

1. **Replace `qwen.qwen3-coder-30b-a3b-v1:0` as the primary validator model.** Use `us.writer.palmyra-x5-v1` (already working as fallback) or `anthropic.claude-3-7-sonnet-*` for the validator role. Qwen has now failed the same way twice in different player sessions (May 18 nemotron, June 25 qwen) — this is a class of failure, not a one-off.

2. **Add a verbatim assertion check before declaring Rule #3 violation.** The model must explicitly cite the data field where the NPC was found. If it cannot cite `playerOwnedNpcs`, `other_players.players[*].name`, `defeatedNpcs`, `recentHistory`, or any `mapTiles[*].ruler`/character reference, the violation is invalid and the check should be auto-PASS.

3. **Add a verbatim Quote-Rule pre-check before any Rule #1 violation.** Strip the quoted dialogue from the user prompt and re-evaluate the unquoted remainder. If the unquoted remainder has no Rule #1 violation content, the Rule #1 violation is invalid. Qwen specifically flags quoted text as a violation despite the MANDATORY rule saying it is automatically legal.

4. **Add a contradiction check between compliance-officer passes.** When the first compliance officer says `isValid: true` and the second says `isValid: false` with an explicit "the action appears to be legal" assessment, surface the contradiction for human review instead of cascading to PIPE_FAILURE.

5. **Add a "rulebook-grounded" verification prompt.** Take the validator's `changesToMake` text and the system prompt's rule definitions and ask a separate model: "For each rule cited, find the exact text in the system prompt that supports the citation. If no such text exists, the citation is hallucinated." This catches the qwen failure mode directly.

6. **Distinguish "schema failure" from "rule violation" in trace colors/labels.** Both currently cascade through `VALIDATION_FAILURE` → `PIPE_FAILURE` → terminate flag. They have very different meanings. The first is a model bug (fixable by switching models). The second is a real game-balance call. Don't conflate them in dashboards.

## User Context (2026-06-25)

- User shut the game down after the validator produced the wrong verdict.
- The action was 100% legal under every rule in the system prompt. The user was correct to be upset.
- The Palmyra fallback model produced a correct rewrite that preserved the play, so the game could have continued.
- The user wants to know "what happened, and how and why the agent broke the rules" — not just "the model misbehaved." Surface the specific prompt exceptions the model violated with quotes from the system prompt.
- The Lord Maple Tree character description is "Evil sentient maple tree seeking to bring maple syrup and Canadian culture by any means necessary. No scheme or plot is too absurd, to unethical, or too evil for Lord Maple Tree. He commands his ent army, and loyal followers of maple syrup do his bidding." Note: ent army is a standard capability for an evil sentient maple tree lord.
- This is the SECOND time the validator has failed on Lord Maple Tree's turn. The pattern is consistent: the validator over-enforces, the meta-validator rubber-stamps or contradicts, the user gets a broken experience.
