# TPipe + AWS Bedrock Error Patterns

## Common API Errors in TPipe Traces

### `missing field 'messages'` — malformed Converse API request
- **Meaning**: The Bedrock pipe serializes a request without the required `messages` array field
- **Likely cause**: Pipe using wrong API format (invoke vs converse), or messages field not populated before call
- **Model context**: Often appears with `nvidia.nemotron-nano-3-30b` or similar non-Claude models
- **Severity**: Root cause — can cascade into VALIDATION_FAILURE and PIPE_FAILURE downstream

### `Text completion requests are not supported. Please use chat completion`
- **Meaning**: A pipe configured for legacy text completion called a model/inference-profile that only supports Converse API
- **Likely cause**: Mismatched `useConverseApi()` setting on the pipe vs what the inference profile expects
- **Model context**: Common with `us.writer.palmyra-x5` and similar Bedrock inference profiles
- **Severity**: Root cause on branch pipes — check `useModelReasoning` and API format settings

### `validation_error`
- **Meaning**: Bedrock rejected the request structure, not the content
- **Likely cause**: Request body malformed before serialization

## Failure Cascade Patterns

### Pattern 1: API error -> Validator false -> PIPE_FAILURE
1. `API_CALL_FAILURE` (malformed request or response parse error)
2. `VALIDATION_FAILURE` on validator pipe (`validationResult: false, reason: Validation function returned false`)
3. `PIPE_FAILURE` on validator pipe
4. `VALIDATION_FAILURE` on parent pipe (`reason: Validator pipe returned content with terminate flag`)
5. `PIPE_FAILURE` on parent pipe

### Pattern 2: Branch pipe mismatch -> cascade
1. Same root API error as Pattern 1
2. `BRANCH_PIPE_TRIGGERED` fires (system attempting fallback)
3. Branch pipe hits `API_CALL_FAILURE` (often text completion error on Converse-only model)
4. Branch VALIDATION_FAILURE -> PIPE_FAILURE
5. Parent PIPE_FAILURE

### Pattern 3: Kotlin structured-concurrency cancellation (NOT an AI refusal)

Observed 2026-06-19 in Round 1 Turn 3 (Bigwang AI_Player_Takeover). Four
failures fired in this exact order:

1. `PIPE_FAILURE` on `Synthesis Stage (Bigwang)` (no error metadata)
2. `PIPE_FAILURE` on `author` (no error metadata)
3. `API_CALL_FAILURE` on `author` — error: `DeferredCoroutine was cancelled`
4. `API_CALL_FAILURE` on `author` — error: `DeferredCoroutine was cancelled`

**This is NOT an AI refusal or a Bedrock error.** It's Kotlin coroutine
cancellation propagating from the parent job. When the Synthesis Stage's
parent coroutine was cancelled (timeout, parent job failure, or external
shutdown), all child coroutines were cancelled in structured-concurrency
fashion. The child `author` pipe's in-flight Bedrock call gets cancelled
mid-flight, and `DeferredCoroutine was cancelled` is what surfaces in
the API call's error field.

**Recognition rules:**
- Two or more `API_CALL_FAILURE` events with `DeferredCoroutine was cancelled`
  in the same turn — strong signal of cancellation, not refusal
- Parent `PIPE_FAILURE` events with empty `error` metadata — also cancellation
  (a real API refusal would have error text from the model or Bedrock)
- No `reason:` field in metadata — refusals populate this; cancellations don't
- All four events share the same `pipeId` lineage or have a clear parent→child
  pipe hierarchy

**Diagnostic action:** check the turn's `TurnResolutionSplitter/trace.json`
for the splitter's `PARALLEL_CANCEL` or `SPLITTER_FAILURE` events, and
check `~/.autogenesis/logs/*.log` for `JobCancellationException` or
`PipelineCancellationException`. The cancellation source is usually a
timeout on the synthesis/branch pipe or a session-level shutdown that
the AI_Player_Takeover didn't recover from.

**Differentiation from AI refusals:** Qwen refusals look like
`{"refusal": "..."}` in the API response body, or `stopReason: refusal`
in Bedrock metadata. They show up as `API_CALL_FAILURE` with the refusal
text in `metadata.Error` or `metadata.refusal`. The error string is
human-readable explanation, not `DeferredCoroutine was cancelled`.

### Pattern 4: Schema failure masquerading as rule violation (terminate-flag cascade)

Observed 2026-06-25 in Round 1 Turn 0 (Lord Maple Tree validator trace).
This is NOT a rule violation, NOT a refusal, NOT a cancellation — it's
a model that produced output that doesn't match the expected schema,
which then cascades through the validator pipeline as if the action were
illegal.

**Sequence** (events 86-118 in the trace):
1. Validator declares `isLegal: false` (possibly correctly OR incorrectly — needs separate verification)
2. Rectifier tries to rewrite the action into a legal one
3. Rectifier's output is malformed (missing required schema fields)
4. Rectifier's own validator: `VALIDATION_FAILURE` with `reason: Validation function returned false`
5. Rectifier: `PIPE_FAILURE`
6. Parent pipe: `VALIDATION_FAILURE` with `reason: Validator pipe returned content with terminate flag`
7. Pipeline falls back to a different model (in this case Palmyra Writer)

**Critical diagnostic rule:** the `terminate flag` in step 6 is set by
the schema-mismatch in step 3, NOT by the rulebook. The original action
may have been 100% legal. The second compliance officer in the chain
often EXPLICITLY notes this: look for assessment text containing phrases
like "the input action appears to be legal" or "no explicit violations
of the five rules listed" — if present, the action was legal and the
cascade is a schema problem.

**Differentiation from Pattern 1 (real rule violation):**
- Pattern 1 cascade: API_CALL_FAILURE → VALIDATION_FAILURE → PIPE_FAILURE → terminate flag
  (starts with a Bedrock API error)
- Pattern 4 cascade: VALIDATION_FAILURE (no API error) → PIPE_FAILURE → terminate flag
  (starts with a schema mismatch from the rectifier pipe)

**Diagnostic action:** when you see a terminate flag, ALWAYS check the
second compliance officer's assessment text before concluding the
action was illegal. If it says the action was legal, report "the
validator pipeline failed due to a schema mismatch — the original
action was likely legal" rather than "the validator rejected the play."

See `references/validator-model-debugging-2026-06-25.md` for the full
walkthrough of this failure mode and the dual-compliance-officer
contradiction pattern (first officer says isValid:true, second says
isValid:false with explicit "action appears to be legal" — current
pipeline picks the worse verdict and cascades).

## Reading Metadata in HTML Traces

TPipe HTML traces concatenate metadata fields into single strings when rendered in table cells. Example:
```
validationResult: falsereason: Validation function returned falsepipeClass: bedrockPipe.BedrockMultimodalPipemodel: nvidia.nemotron-nano-3-30bprovider: Aws...
```
Use targeted regex extraction rather than iterating metadata keys:
```bash
# Extract just the error message
grep -oP '"Error":\s*\{[^}]+\}' trace.html | head -5

# Extract validation reason
grep -oP 'reason:[^a-z][^A-Z]*([^.])' trace.html | head -5
```

## Pipe Model Reference (this workspace)
| Model | API Format | Notes |
|-------|-----------|-------|
| `nvidia.nemotron-nano-3-30b` | Converse | Can hit 'missing messages' if serialize wrong. **Unfit for validator role** — see `references/validator-model-debugging.md` |
| `qwen.qwen3-coder-30b-a3b-v1:0` | Converse | **Unfit for validator role** — see `references/validator-model-debugging-2026-06-25.md`. Ignores Quote Rule and Rule #3 Part A, over-enforces. `useModelReasoning: false` so no reasoning trail. |
| `anthropic.claude-3-7-sonnet-*` | Converse | Most reliable |
| `us.anthropic.claude-haiku-4-5-*` | Converse | Better than qwen for compliance-officer role. Used as fallback. |
| `arn:aws:bedrock:us-west-2:...inference-profile/us.writer.palmyra-x5*` | Converse ONLY | Text completion will fail. **Working fallback for validator role** — handles schema correctly. |
| `us.writer.palmyra-x5-v1:0` | Converse ONLY | Same as above |
