# TraceEventType Reference

Complete reference of all TraceEventType values (~95 types after 2026-07-08 PumpStation vocabulary addition) organized by category.

**2026-07-08 v1.6 patch**: Added the entire PumpStation sealed event family (PUMP_STATION_*) — 13 event types with key-meta-fields table + 4 parsing pitfalls. Before this patch the reference had zero PumpStation entries, forcing triage agents to re-derive the vocabulary via `grep -oE 'PUMP_STATION_[A-Z_]+'`. Worktree of third-pass PumpStation triage at `/home/cage/.hermes/plans/pumpstation-third-pass-triage-2026-07-08.md`.

---

## Pipe Events

Events related to individual pipe execution.

| Event Type | Description |
|------------|-------------|
| `PIPE_START` | Pipe execution started |
| `PIPE_END` | Pipe execution ended |
| `PIPE_SUCCESS` | Pipe completed successfully |
| `PIPE_FAILURE` | Pipe failed with error |
| `PIPE_TIMEOUT` | Pipe timed out |
| `PIPE_RETRY` | Pipe retry attempted |
| `CONTEXT_PULL` | Context data pulled from memory |
| `CONTEXT_TRUNCATE` | Context truncated due to token limit |
| `CONTEXT_PREPARED` | Context preparation completed |
| `PRE_INVOKE` | Pre-invocation validation/check |
| `POST_GENERATE` | Post-generation processing |
| `VALIDATION_START` | Validation phase started |
| `VALIDATION_SUCCESS` | Validation passed |
| `VALIDATION_FAILURE` | Validation failed |
| `TRANSFORMATION_START` | Transformation phase started |
| `TRANSFORMATION_SUCCESS` | Transformation completed |
| `TRANSFORMATION_FAILURE` | Transformation failed |
| `API_CALL_START` | External API call initiated |
| `API_CALL_SUCCESS` | API call completed successfully |
| `API_CALL_FAILURE` | API call failed |
| `BRANCH_PIPE_TRIGGERED` | Branch pipe activated |
| `PIPELINE_TERMINATION` | Pipeline terminated |

### Pause/Resume Events

| Event Type | Description |
|------------|-------------|
| `PIPELINE_PAUSE` | Pipeline paused |
| `PIPELINE_RESUME` | Pipeline resumed |
| `PAUSE_POINT_CHECK` | Pause point validation |

---

## Manifold Orchestration Events

Events related to multi-agent orchestration via Manifold container.

### Lifecycle

| Event Type | Description |
|------------|-------------|
| `MANIFOLD_START` | Manifold orchestration started |
| `MANIFOLD_END` | Manifold orchestration ended |
| `MANIFOLD_SUCCESS` | Manifold completed successfully |
| `MANIFOLD_FAILURE` | Manifold failed with error |
| `MANIFOLD_INIT_CHECK` | Manifold initialization check |

### Manager Decision Events

| Event Type | Description |
|------------|-------------|
| `MANAGER_DECISION` | Manager made a decision |
| `MANAGER_TASK_ANALYSIS` | Manager analyzed task |
| `MANAGER_AGENT_SELECTION` | Manager selected agent |

### Task Progress Events

| Event Type | Description |
|------------|-------------|
| `TASK_PROGRESS_UPDATE` | Task progress updated |
| `TASK_COMPLETION_CHECK` | Task completion checked |
| `TASK_NEXT_STEPS` | Next steps determined |

### Agent Communication Events

| Event Type | Description |
|------------|-------------|
| `AGENT_DISPATCH` | Agent dispatched with task |
| `AGENT_RESPONSE` | Agent responded with result |
| `AGENT_REQUEST_VALIDATION` | Agent request validated |
| `AGENT_REQUEST_EXTRACTION` | Agent request extracted |
| `AGENT_RESPONSE_PROCESSING` | Agent response being processed |

### Loop Events

| Event Type | Description |
|------------|-------------|
| `MANIFOLD_LOOP_ITERATION` | Loop iteration executed |
| `MANIFOLD_TERMINATION_CHECK` | Loop termination checked |
| `MANIFOLD_LOOP_LIMIT_EXCEEDED` | Loop limit exceeded |

### Error Events

| Event Type | Description |
|------------|-------------|
| `AGENT_REQUEST_INVALID` | Agent request invalid |
| `MANIFOLD_RECOVERY_ATTEMPT` | Recovery attempt in progress |

---

## Splitter Orchestration Events

Events related to parallel pipeline execution via Splitter container.

### Lifecycle

| Event Type | Description |
|------------|-------------|
| `SPLITTER_START` | Splitter orchestration started |
| `SPLITTER_END` | Splitter orchestration ended |
| `SPLITTER_SUCCESS` | Splitter completed successfully |
| `SPLITTER_FAILURE` | Splitter failed with error |

### Content Distribution

| Event Type | Description |
|------------|-------------|
| `SPLITTER_CONTENT_DISTRIBUTION` | Content distributed to branches |
| `SPLITTER_PIPELINE_DISPATCH` | Pipeline dispatched to branch |
| `SPLITTER_PIPELINE_COMPLETION` | Pipeline branch completed |

### Callback Events

| Event Type | Description |
|------------|-------------|
| `SPLITTER_PIPELINE_CALLBACK` | Branch pipeline callback |
| `SPLITTER_COMPLETION_CALLBACK` | Completion callback triggered |

### Parallel Execution Events

| Event Type | Description |
|------------|-------------|
| `SPLITTER_PARALLEL_START` | Parallel execution started |
| `SPLITTER_PARALLEL_AWAIT` | Awaiting parallel completion |
| `SPLITTER_RESULT_COLLECTION` | Results collected from branches |

---

## Junction Orchestration Events

Events related to collaborative discussion via Junction container.

### Lifecycle

| Event Type | Description |
|------------|-------------|
| `JUNCTION_START` | Junction orchestration started |
| `JUNCTION_END` | Junction orchestration ended |
| `JUNCTION_SUCCESS` | Junction completed successfully |
| `JUNCTION_FAILURE` | Junction failed with error |
| `JUNCTION_PAUSE` | Junction paused |
| `JUNCTION_RESUME` | Junction resumed |

### Round Events

| Event Type | Description |
|------------|-------------|
| `JUNCTION_ROUND_START` | Discussion round started |
| `JUNCTION_ROUND_END` | Discussion round ended |
| `JUNCTION_VOTE_TALLY` | Votes tallied |
| `JUNCTION_CONSENSUS_CHECK` | Consensus check performed |

### Participant Events

| Event Type | Description |
|------------|-------------|
| `JUNCTION_PARTICIPANT_DISPATCH` | Participant dispatched |
| `JUNCTION_PARTICIPANT_RESPONSE` | Participant responded |

### Workflow Events

| Event Type | Description |
|------------|-------------|
| `JUNCTION_WORKFLOW_START` | Workflow started |
| `JUNCTION_WORKFLOW_END` | Workflow ended |
| `JUNCTION_WORKFLOW_SUCCESS` | Workflow succeeded |
| `JUNCTION_WORKFLOW_FAILURE` | Workflow failed |
| `JUNCTION_PHASE_START` | Phase started |
| `JUNCTION_PHASE_END` | Phase ended |
| `JUNCTION_HANDOFF` | Handoff to next phase |

---

## DistributionGrid Orchestration Events

Events related to distributed node routing via DistributionGrid container.

### Lifecycle

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_INIT` | Grid initialization |
| `DISTRIBUTION_GRID_VALIDATION_START` | Validation started |
| `DISTRIBUTION_GRID_VALIDATION_SUCCESS` | Validation passed |
| `DISTRIBUTION_GRID_VALIDATION_FAILURE` | Validation failed |
| `DISTRIBUTION_GRID_PAUSE` | Grid paused |
| `DISTRIBUTION_GRID_RESUME` | Grid resumed |
| `DISTRIBUTION_GRID_RUNTIME_RESET` | Runtime reset |
| `DISTRIBUTION_GRID_START` | Grid started |
| `DISTRIBUTION_GRID_END` | Grid ended |
| `DISTRIBUTION_GRID_SUCCESS` | Grid succeeded |
| `DISTRIBUTION_GRID_FAILURE` | Grid failed |

### Router Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_ROUTER_DECISION` | Router decision made |

### Worker Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_LOCAL_WORKER_DISPATCH` | Local worker dispatched |
| `DISTRIBUTION_GRID_LOCAL_WORKER_RESPONSE` | Local worker responded |

### Peer Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_PEER_HANDOFF` | Handoff to peer |
| `DISTRIBUTION_GRID_PEER_RESPONSE` | Peer responded |

### Return Routing

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_RETURN_ROUTING` | Return routing determined |

### Memory Envelope

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_MEMORY_ENVELOPE` | Memory envelope processed |

### Policy Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_POLICY_EVALUATION` | Policy evaluated |

### Session Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_SESSION_HANDSHAKE` | Session handshake completed |

### Loop Guard

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_LOOP_GUARD` | Loop guard evaluated |

### Registry Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_BOOTSTRAP_CATALOG_PULL` | Bootstrap catalog pulled |
| `DISTRIBUTION_GRID_DISCOVERY_ADMISSION` | Discovery admission processed |
| `DISTRIBUTION_GRID_REGISTRY_PROBE` | Registry probed |
| `DISTRIBUTION_GRID_REGISTRY_REGISTRATION` | Registry registration |
| `DISTRIBUTION_GRID_REGISTRY_LEASE_RENEWAL` | Registry lease renewed |
| `DISTRIBUTION_GRID_REGISTRY_QUERY` | Registry queried |

### Durability Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_DURABILITY_CHECKPOINT` | Durability checkpoint created |

### Public Listing Events

| Event Type | Description |
|------------|-------------|
| `DISTRIBUTION_GRID_PUBLIC_LISTING` | Public listing created |
| `DISTRIBUTION_GRID_PUBLIC_LISTING_AUTO_RENEW` | Public listing auto-renewed |

---

## P2P Communication Events

Events related to peer-to-peer agent communication.

| Event Type | Description |
|------------|-------------|
| `P2P_REQUEST_START` | P2P request started |
| `P2P_REQUEST_SUCCESS` | P2P request succeeded |
| `P2P_REQUEST_FAILURE` | P2P request failed |
| `P2P_TRANSPORT_SEND` | Transport send initiated |
| `P2P_TRANSPORT_RECEIVE` | Transport receive completed |
| `PCP_CONTEXT_TRANSFER` | Context transferred via PCP |

---

## KillSwitch Safety Events

Events related to token limit safety mechanisms.

| Event Type | Description |
|------------|-------------|
| `KILLSWITCH_CHECK` | KillSwitch token limit checked |
| `KILLSWITCH_TRIPPED` | KillSwitch triggered, execution stopped |

---

## Event Type Count

Total: ~95 unique event types across all categories (PumpStation added 13 in 2026-07-08)

| Category | Count |
|----------|-------|
| Pipe | ~25 |
| Manifold | ~15 |
| Splitter | ~10 |
| Junction | ~15 |
| DistributionGrid | ~20 |
| P2P | ~6 |
| KillSwitch | ~2 |
| PumpStation | ~13 (see section above) |

## See Also

- [trace-formats.md](trace-formats.md) - Format documentation
- [console_trace.md](console_trace.md) - CONSOLE format parsing
- [bedrock-errors.md](bedrock-errors.md) - AWS Bedrock error patterns

| Event Type | Description | Key meta fields |
|------------|-------------|-----------------|
| `PUMP_STATION_STARTED` | Harness execution started (emitted once per run) | (none — meta `{}`) |
| `PUMP_STATION_COMPLETED` | Harness succeeded | `exitReason` (`JudgeComplete`/`PassSignal`/`GoalValidationFailed`), `finalOutput` (MultimodalContent) |
| `PUMP_STATION_FAILED` | Harness failed (5 error classes only: `MaxTurnsExceeded`, `KillSwitchTripped`, `P2PRequestInvalid`, `InitNotCalled`, `CompactionInflated`) | `error`, `errorMessage`, `exitReason` |
| `PUMP_STATION_HARNESS_WARNING` | Non-fatal advisory at pre-init (e.g. `NoExitSignalConfigured` when no judge/FlagTriggered/path-exit wired) | `warningCode`, `message` |
| `PUMP_STATION_JUDGE_STARTED` / `JUDGE_COMPLETED` / `JUDGE_SKIPPED` | Judge phase events; `SKIPPED.reason` is `first_turn` (Always mode + turn 0) or `no_flag_set` (FlagTriggered mode + flag clear). `no_flag_set` ALWAYS wins over `first_turn` per oracle | `isComplete`, `shouldTerminate`, `reason`/`reasonText`, `judgeRunMode`, `inputTokens`/`outputTokens`/`totalTokens` |
| `PUMP_STATION_DISPATCH_STARTED` / `DISPATCH_COMPLETED` | Dispatch phase events | `selectedPathName`, `pathRequest`, `contentPreview`, `contentLength`, tokens |
| `PUMP_STATION_PATH_SELECTED` / `PATH_STARTED` / `PATH_COMPLETED` / `PATH_FAILED` | Path lifecycle. `PATH_FAILED.error` carries the failure class (`LoopGuardTriggered`, `PathExecutionException`, `PathTimeout`, etc.) | `pathName`, `riskLevel`, `error`, `errorMessage` |
| `PUMP_STATION_PATH_SAFETY_STARTED` / `PATH_SAFETY_COMPLETED` | Path-safety gate events (only fires when `pathSafetyAgent`/`pathSafetyFunction` is configured) | `pathName`, `riskLevel`, `approved`, `reason` |
| `PUMP_STATION_MEMORY_UPDATE_STARTED` / `MEMORY_UPDATE_COMPLETED` | Memory phase events | `memoryMode` (`Compaction`/`Stash`/`LoreBook`), `compactionPercent`, `loreBookActive`, `summaryActive` |
| `PUMP_STATION_COMPACTION_STARTED` / `COMPACTION_COMPLETED` | Compaction phase; `COMPLETED.result` is `Applied`, `DiscardedPreEmpted`, `Inflated`, or `HandedOffToTruncation` | `strategy` (`Hybrid`/`Whole`/`Chunked`), `memoryMode`, `previousHistorySize`, `newHistorySize`, `result`, `attempt`, `fanout` |
| `PUMP_STATION_LOOP_GUARD_TRIPPED` | Loop guard fired (e.g. `maxConsecutiveSamePath`, `maxTotalPathCallsPerPath`). Counter values live in `detail` as a PACKED STRING `"consecutive=N, limit=M"` — NOT separate meta keys. Parse with `dict(p.split("=", 1) for p in detail.split(", ") if "=" in p)` | `guard`, `pathName`, `detail` (packed string!) |
| `PUMP_STATION_INTERVENTION_STARTED` / `INTERVENTION_COMPLETED` | Intervention agent fired after loop-guard trip | `trigger`, `pathName`, `nudges`, `shouldContinue`, `result`, tokens |
| `PUMP_STATION_GOAL_VALIDATION_STARTED` / `GOAL_VALIDATION_COMPLETED` | Optional goal-validation phase (only when `goalAgent` is configured) | `passed`, `reason` |
| `PUMP_STATION_HARNESS_PAUSED` / `HARNESS_RESUMED` | User-initiated pause/resume at `checkPauseGuards` boundaries (`BeforeJudge`, `BeforePathExecution`, `BeforeGoalValidation` are the only three supported phases per oracle — other phases' pause is silently ignored) | `phase` |

### PumpStation-specific parsing pitfalls

1. **Observer fires twice** — every `PumpStationEvent` appears twice in parsed JSON. `COMPACTION_COMPLETED` count is `2 × COMPACTION_STARTED` count. Do not naively subtract. Pinned behavior, not a bug.
2. **Loop-guard `detail` is a packed string** — `consecutive` and `limit` are NOT separate meta keys. They live in `meta.detail = "consecutive=N, limit=M"`. Until `PumpStationHelpers.kt` splits them into separate keys, callers must split the string.
3. **`runFinalizationPhase` fallback** — when `taskState.exitReason` is null at HarnessCompleted emit time, the source at `src/main/kotlin/Pipeline/PumpStationLoop.kt:2666` falls back to `PumpStationExitReason.JudgeComplete`. Legacy traces (pre-2026-07-08) may show `exitReason=None` or empty meta because the `HarnessCompleted` model didn't carry these fields yet. Schema evolved; current model has both `exitReason` and `finalOutput`.
4. **HarnessFailed only fires for 5 error classes** — `MaxTurnsExceeded`, `KillSwitchTripped`, `P2PRequestInvalid`, `InitNotCalled`, `CompactionInflated`. `LoopGuardTriggered` and `PathExecutionException` from a path funnel emit `PathFailed` and the loop CONTINUES — they are NOT harness-level failures.

## See Also

- [trace-formats.md](trace-formats.md) - Format documentation
- [console_trace.md](console_trace.md) - CONSOLE format parsing
- [bedrock-errors.md](bedrock-errors.md) - AWS Bedrock error patterns