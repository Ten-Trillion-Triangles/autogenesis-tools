# MultimodalContent Flow Control Flags

Source: `/home/cage/Desktop/Workspaces/TPipe/TPipe/src/main/kotlin/Pipe/BinaryContent.kt:118-181`

`MultimodalContent` is the data class that flows through a pipeline. Every pipe receives it and can set control flags on it to redirect execution at runtime. The flags live on the content object itself, not on the pipeline.

## The flags

| Flag | What it does |
|------|-------------|
| `terminatePipeline` | Halt the pipeline cleanly. Not an error. Early exit. |
| `repeatPipe` | Re-call this pipe with the same content. Keeps calling until you set it false. |
| `passPipeline` | Exit early without being an error. The task is done, skip remaining steps. |
| `jumpToPipe` | Jump to a named pipe (forward or backward). Private — use `content.metadata["jumpToPipe"] = "pipe-name"`. |
| `interuptPipeline` | Fires interrupt signal for PumpStation harness system. Used by specialized agents to trigger intervention paths at specific harness cycle points. |
| `skipReasoningPipe` | Skip the reasoning sub-pipe for this turn. Useful when token budget didn't need compression and running the reasoning pipe would waste tokens. |
| `metadata` | Scratch pad map. The Connector uses `metadata["connectorPath"]` for routing. Any key-value pairs for downstream pipes. |

## The pipeline reads these flags

After every pipe execution, the pipeline evaluates these flags in order and takes the appropriate action. A pipe can set multiple flags simultaneously.

## The Connector routing mechanism

The Connector uses `metadata["connectorPath"]` as the routing key — not a method on the content class directly.

```kotlin
// How a pipe sets the routing key
content.metadata["connectorPath"] = "positive"

// How Connector reads it (Connector.kt:392-403)
fun MultimodalContent.getConnectorPath(): Any? = metadata["connectorPath"]
fun MultimodalContent.setConnectorPath(path: Any) { metadata["connectorPath"] = path }
```

The Connector at runtime:
```kotlin
val key = content.getConnectorPath()
if (key == null || !branches.contains(key)) {
    content.terminatePipeline = true  // no matching branch → halt
} else {
    return execute(key, content)  // route to matching branch
}
```

## terminatePipeline is not an exception

`terminatePipeline` sets a boolean flag. It does not throw. Downstream code checks the flag after the pipe returns — do not use try/catch. The Connector sets the flag, it doesn't throw.

## Convenience methods on MultimodalContent

```kotlin
content.terminate()        // sets terminatePipeline = true
content.interupt()         // sets interuptPipeline = true
content.repeat()           // sets repeatPipe = true
content.addText("...")     // appends to text
content.addBinary(...)     // adds binary content
```

## Key source locations

- `TPipe/src/main/kotlin/Pipe/BinaryContent.kt:118-181` — `MultimodalContent` data class with all flags
- `TPipe/src/main/kotlin/Pipe/BinaryContent.kt:218-237` — convenience methods (`terminate()`, `interupt()`, `repeat()`)
- `TPipe/src/main/kotlin/Pipeline/Connector.kt:392-403` — `setConnectorPath`/`getConnectorPath` extension functions
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:6064-6067` — pipeline flag evaluation after each pipe execution