# MultimodalContent flow control flags

MultimodalContent is the data carrier between pipes in a TPipe Pipeline. After each pipe executes, the Pipeline reads the content's control flags to decide what happens next. Every pipe can set these flags — the Pipeline never sets them.

Source: `TPipe/src/main/kotlin/Pipe/BinaryContent.kt:118-181` (MultimodalContent data class) and `TPipe/src/main/kotlin/Pipeline/Pipeline.kt:1162-1215` (`getNextPipe()`).

## The flags

| Flag | What it does |
|------|-------------|
| `terminatePipeline` | Halt the pipeline cleanly. Not an error. Early exit. |
| `passPipeline` | Exit early without being an error. Task is done. |
| `repeatPipe` | Re-call this pipe with the same content. Keeps getting called until you set it to `false`. |
| `jumpToPipe` | Redirect execution. See below. |
| `skipReasoningPipe` | Skip the reasoning sub-pipe for this turn. |
| `interuptPipeline` | Fire an interrupt signal for the PumpStation harness system. |
| `metadata` | Scratch pad map. `Connector` uses `metadata["connectorPath"]` for routing. Any pipe can read/write anything here. |

## `jumpToPipe` — the redirection primitive

This is the key flag for non-linear pipelines. The `getNextPipe()` function at `Pipeline.kt:1162-1215` handles it:

```kotlin
fun getNextPipe(content: MultimodalContent) : Pipe?
{
    val jumpTarget = content.getJumpToPipe()

    // Empty string → sequential (next pipe in list)
    if(jumpTarget.isEmpty()) {
        return pipes[currentPipeIndex]
    }

    // "skip-to-next-pipe" → skip ahead one
    if(jumpTarget == "skip-to-next-pipe") {
        currentPipeIndex++
        return pipes[currentPipeIndex]
    }

    // Named pipe → jump to that pipe by name lookup (forward or backward)
    val namedPipe = getPipeByName(jumpTarget)
    currentPipeIndex = namedPipe.first
    return namedPipe.second
}
```

Three modes:
- `""` (empty) → sequential, next pipe in the list
- `"skip-to-next-pipe"` → skip ahead one
- `"pipe-name"` → jump to that named pipe (can go forward or backward in the pipeline)

## `repeatPipe` loop

At `Pipeline.kt:1434-1447`:

```kotlin
while(generatedContent.repeatPipe)
{
    var repeatPipeResult : Deferred<MultimodalContent> = async {
        pipe.execute(generatedContent)
    }
    generatedContent = repeatPipeResult.await()
}
```

The pipe keeps getting called with the same content object until `repeatPipe = false` is set. Useful for custom reasoning loops.

## Priority order

After each pipe execution (`Pipeline.kt` around lines 1449-1501):

1. Check `repeatPipe` — loop if true
2. Check `terminatePipeline` → break pipeline
3. Check `passPipeline` → break pipeline (if `jumpToPipe` is also set, jump takes priority)
4. Process `jumpToPipe` → redirect
5. Otherwise: `currentPipeIndex++`, next pipe

`passPipeline` + `jumpToPipe`: jump takes priority over pass (`Pipeline.kt:1490-1492`).

## The Connector — convenience, not the primitive

The `Connector` at `TPipe/src/main/kotlin/Pipeline/Connector.kt` is a Pipeline component that implements key-based routing. It reads `content.metadata["connectorPath"]` to find the routing key and dispatches to a matching branch:

```kotlin
fun MultimodalContent.setConnectorPath(path: Any) {
    metadata["connectorPath"] = path
}

fun MultimodalContent.getConnectorPath() : Any? {
    return metadata["connectorPath"]
}
```

The Connector sets `terminatePipeline` if no branch matches. It never throws.

**The primitive is `jumpToPipe`.** Any pipe can directly set `content.jumpToPipe = "some-pipe-name"` to redirect execution without going through the Connector. The Connector is a convenience pattern for key-based dispatch; `jumpToPipe` is the direct control.