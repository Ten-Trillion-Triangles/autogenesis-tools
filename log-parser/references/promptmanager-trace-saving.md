# PromptManager Trace Save Patterns

## The Correct Pattern (After Fix)

```kotlin
// Success path — trace saved AFTER extractJson(), so parsing failures don't lose traces
val result = pipe.execute()  // may throw on validation failure
val extracted = extractJson<T>(result.text)  // may return null
saveAgentTrace("AgentType", connectionId, pipe)  // saved even if extractJson returns null
return extracted  // null if parsing failed — caller handles null return

// Catch path — trace saved so failure runs still have traces
try {
    val result = pipe.execute()
    return extractJson<T>(result.text)
} catch (e: Exception) {
    saveAgentTrace("AgentType", connectionId, pipe)  // guarantee trace exists for failures
    throw e  // rethrow so caller knows it failed
}
```

## The Broken Pattern (Before Fix)

```kotlin
saveAgentTrace("AgentType", connectionId, pipe)  // called BEFORE extractJson
return extractJson<T>(result.text)  // if this throws, trace already saved but catch block has no trace
```

## Why This Matters

**If validation throws BEFORE `saveAgentTrace()` is called:**
- No trace files written for this run
- Log entries may show trace references from PREVIOUS runs (confusing during investigation)
- Model never received the context you think it did — but you can't verify because no trace exists

**If `saveAgentTrace()` is called BEFORE `extractJson()`:**
- Success run: trace saved, but if extractJson returns null (parsing fails), trace was saved for a null result
- Failure run: trace NOT saved (exception thrown before save call)

**After the fix (save after extractJson + in catch):**
- Success run: trace saved with valid result
- Parsing failure: trace saved with null result (trace shows what model output)
- Exception: trace saved in catch block

## Debugging Missing Traces

When investigating why a trace doesn't exist:

1. Check the log for the exact timestamp of the run — old runs may have been cleaned up
2. Check if validation threw before `saveAgentTrace()` was reached
3. Check if the trace directory was created but empty (partial save)
4. Verify the log entry's file path pattern matches actual files on disk

**In Autogenesis:** `~/.autogenesis/logs/*.log` contains entries like:
```
Saved agent traces (JSON/HTML) to .../Round_1_Turn_0_PlayerName/AgentType/connectionId/baseFileName.*
```
If this entry exists but `~/.tpipe/debug/trace/` has no matching files → code threw before save call.