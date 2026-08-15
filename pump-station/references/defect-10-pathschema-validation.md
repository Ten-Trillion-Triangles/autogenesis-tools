# Defect 10 — Dispatch-emitted pathSchema becomes literal path prompt (warn-and-continue contract)

The dispatch LLM emits a `pathRequest.pathSchema` field that is meant to carry the path's input shape. A chat-mode LLM can freely emit non-JSON content there (e.g. `"pathSchema": "Hello I am not valid JSON"`). The pre-fix `buildPathInput` at `PumpStationLoop.kt:617` concatenated that string verbatim into the path LLM's prompt — so the path obediently researched the schema text instead of the user's topic. Live trace 03 showed the gather-pipe receiving `"PathRequest"` as input (the dispatch LLM emitted `"pathSchema": "PathRequest"` and the path researched the string instead of the research topic).

**The canonical user pattern is pathName-only dispatch where `path.pathSchema` is the canonical source-of-truth.** The dispatch output's `pathSchema` is an edge case for runtime-customized schemas. Don't paper over harness gaps by bypassing this surface in TDD tests.

## The warn-and-continue fix contract

`PumpStationLoop.kt` `buildPathInput` + `PumpStationHelpers.kt` `buildPathSchemaFallbackMessage`:

1. **Validate the dispatch-emitted schema** before merging it with the user's input. Round-trip through `extractJson<PathRequest>` (or `Json.parseToJsonElement(...)` + `is JsonObject` if the kotlinx-serialization plugin is unavailable in your sandbox). On parse failure, treat as garbage.
2. **Append a `[Harness Notice]` hint to `turnHistory`** so the next dispatch LLM sees the constraint. The helper `buildPathSchemaFallbackMessage` (mirrors `buildInvalidPathRequestMessage`'s wrapper style) accepts `details` map with `pathName` + `output` (the raw garbage text).
3. **Fall back to `path.pathSchema` (the canonical source-of-truth)** as the authoritative input to the path LLM. The path's own `pathSchema` is the user's *intended* schema; the dispatch's garbage string is never concatenated.
4. **Valid dispatch schemas pass through unchanged** — runtime-customized schemas remain supported; only garbage is filtered.

## The TDD test-design rule (operator OOB correction)

"verify the WARN behavior (hint + fallback), not the DEFAULT PATH (which was already correct in source)." A real PumpStation user wires pathSchema through the dispatcher only for runtime customization; for the common case the path's own `pathSchema` is the schema source. The test design must drive the WARN behavior, not bypass the designed surface by stubbing the dispatcher or hardcoding the path's pathSchema in a way that hides the dispatcher-emitted schema's role.

Three concrete test patterns the WARN-behavior test must cover (per `PumpStationPathSchemaValidationTest.kt`):

1. `buildPathInput_filters_non_json_dispatch_schema_and_falls_back` — the dispatch-emitted garbage string `"Hello I am not valid JSON"` must NOT appear in the path LLM's inbound `MultimodalContent.text`, the path's canonical schema must appear, and `turnHistory` must grow by one `[Harness Notice]` entry referencing `pathSchema`.
2. `buildPathInput_passes_through_valid_json_dispatch_schema` — regression guard: a valid JSON schema flows through unmodified, no hint appended.
3. `buildPathInput_uses_path_canonical_schema_when_dispatch_blank` — baseline: an empty dispatch `pathSchema` falls back to `path.pathSchema` without firing the hint (empty is the legitimate default).

## Bytecode evidence the patch is in place

When the kotlinx-serialization plugin is unavailable in the sandbox (compile-time evidence):

```bash
javap -c -p -classpath build/classes/kotlin/main com.TTT.Pipeline.PumpStationLoopKt \
  | grep "public static final com.TTT.Pipe.MultimodalContent buildPathInput" -A 80 \
  | grep -E "parseToJsonElement|JsonObject"
# Expected:
#   72: invokevirtual #977  // Method kotlinx/serialization/json/Json$Default.parseToJsonElement
#   79: instanceof    #979  // class kotlinx/serialization/json/JsonObject
```

```bash
javap -p -classpath build/classes/kotlin/main com.TTT.Pipeline.PumpStationHelpersKt \
  | grep buildPathSchemaFallbackMessage
# Expected: public static final java.lang.String buildPathSchemaFallbackMessage(...)
```

## Reference case (2026-07-10, Defect 10 fix)

- `buildPathSchemaFallbackMessage` added at `PumpStationHelpers.kt:910`
- `buildPathInput` rewired at `PumpStationLoop.kt:634-693` (KDoc lines 609-633, JSON-object validity check at 657-660, `effectiveSchema` `when` at 662, `turnHistory.add` fallback at 670-679, original text-merging at 687-695)
- RED test `PumpStationPathSchemaValidationTest.kt` (223 lines, 3 unit tests) drives `buildPathInput` directly via `-Xfriend-paths=build/classes/kotlin/main` because the kotlinx-serialization plugin gap in this sandbox blocks the full `executeLocal` flow through `refreshPipelinesPrompts` → `applySystemPrompt` → `examplePromptFor(PathRequest.serializer())`
- RED→GREEN signal confirmed via hermes-verify- script (`/tmp/hermes-verify-defect10-pathschema.sh`)
- Suite-green status remained unobtainable; documented explicitly as ad-hoc-not-suite-green per the operator convention

## Cross-cutting lesson

The two-file selective recompile trick from `tdd-protoc-grpc-mcp` Lesson 7 is what made this RED→GREEN evidence reachable without breaking T1's path-injection test. When the production patch references but does not modify a `@Serializable` class, `-Xfriend-paths=build/classes/kotlin/main` + selective recompile of just the patched files preserves the precompiled `$$serializer.class` companions. Recompiling the entire `Pipeline/` tree without the serialization plugin silently invalidates them and breaks every test that round-trips through `@Serializable` types.