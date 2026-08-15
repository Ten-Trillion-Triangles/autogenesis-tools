# TPipe Public Surface — Verified Import Map

Generated 2026-06-29 from `/home/cage/Desktop/Workspaces/TPipe/TPipe` branch `main`. Published coord `com.github.ten-trillion-triangles:TPipe:<v>`. This is the import graph a script author needs; pair with `tpipe-scripting/SKILL.md` for the runtime shapes.

## 1. Core imports (published in `com.github.ten-trillion-triangles:TPipe:<v>`)

### `com.TTT.Pipe.*`

```
import com.TTT.Pipe.Pipe                       // abstract base — CANNOT instantiate
import com.TTT.Pipe.DummyPipe                  // no-API stand-in, perfect for smoke tests
import com.TTT.Pipe.MultimodalContent          // data class (text + binaries)
import com.TTT.Pipe.BinaryContent              // sealed class
import com.TTT.Pipe.ProviderInterface
import com.TTT.Pipe.StreamingCallbackBuilder
import com.TTT.Pipe.StreamingCallbackManager
import com.TTT.Pipe.hasError                   // extension on MultimodalContent
```

`Pipe` is `abstract class Pipe : P2PInterface, ProviderInterface` (`src/main/kotlin/Pipe/Pipe.kt:566`). The `class DummyPipe : Pipe()` lives in core and needs no external service — its `generateText(prompt)` is a pass-through.

### `com.TTT.Pipeline.*`

```
import com.TTT.Pipeline.Pipeline
import com.TTT.Pipeline.Connector
import com.TTT.Pipeline.MultiConnector
import com.TTT.Pipeline.Splitter
import com.TTT.Pipeline.Manifold
import com.TTT.Pipeline.Junction
import com.TTT.Pipeline.DistributionGrid
import com.TTT.Pipeline.PumpStation
import com.TTT.Pipeline.PathObject
import com.TTT.Pipeline.ManifoldDslMarker       // DSL hygiene markers
import com.TTT.Pipeline.JunctionDslMarker
import com.TTT.Pipeline.PumpStationDslMarker
import com.TTT.Pipeline.DistributionGridDslMarker
```

### `com.TTT.Context.*`

```
import com.TTT.Context.ContextWindow
import com.TTT.Context.ContextBank
import com.TTT.Context.MiniBank
import com.TTT.Context.Dictionary
import com.TTT.Context.ContextLock
import com.TTT.Context.MemoryIntrospection
import com.TTT.Context.MemoryClient
import com.TTT.Context.MemoryServer
import com.TTT.Context.buildLorebookScanText   // extension on ContextWindow
```

### `com.TTT.P2P.*`

```
import com.TTT.P2P.P2PInterface
import com.TTT.P2P.P2PRegistry
import com.TTT.P2P.P2PHostedRegistry
import com.TTT.P2P.P2PHostedRegistryClient
import com.TTT.P2P.P2PHost
import com.TTT.P2P.P2PStdioHost
import com.TTT.P2P.AgentDescriptor
import com.TTT.P2P.KillSwitch
```

### `com.TTT.PipeContextProtocol.*`

```
import com.TTT.PipeContextProtocol.PcpContext
import com.TTT.PipeContextProtocol.PcpExecutionDispatcher
import com.TTT.PipeContextProtocol.PcPRequest
import com.TTT.PipeContextProtocol.PcpExecutionResult
import com.TTT.PipeContextProtocol.FunctionRegistry
import com.TTT.PipeContextProtocol.bindFunction   // ext on PcpContext
import com.TTT.PipeContextProtocol.bindNativeFunction  // ext on Pipe
```

### `com.TTT.Enums.*`

```
import com.TTT.Enums.ProviderName         // ANTHROPIC, OPENAI, BEDROCK, OLLAMA, GENERIC_OPENAI, OPENROUTER, ...
import com.TTT.Enums.PromptMode
import com.TTT.Enums.PipeRole
import com.TTT.Enums.SummaryMode
import com.TTT.Enums.ContextWindowSettings
```

### Misc

```
import com.TTT.Util.serialize
import com.TTT.Util.deserialize
import com.TTT.Util.examplePromptFor
import com.TTT.Util.extractAllJsonObjects
import com.TTT.Util.repairJsonString
import com.TTT.Debug.PipeTracer
import com.TTT.Debug.TraceConfig
import com.TTT.Structs.PipeSettings       // serialization for save/load
```

## 2. Concrete `Pipe` subclasses — NOT in the core jar

Located in provider modules. Scripts MUST `@file:DependsOn` to reach these.

| Concrete `Pipe` | Module | Maven coord | Constructor |
|---|---|---|---|
| `DummyPipe` | core | `com.github.ten-trillion-triangles:TPipe:<v>` | `DummyPipe()` |
| `BedrockPipe` | `TPipe-Bedrock/` | `com.github.ten-trillion-triangles:TPipe-Bedrock:<v>` | `BedrockPipe()` (lines 67) |
| `BedrockMultimodalPipe` | `TPipe-Bedrock/` | same | `BedrockMultimodalPipe()` |
| `NovaPipe` | `TPipe-Bedrock/` | same | `NovaPipe()` |
| `NovaCanvasPipe` | `TPipe-Bedrock/` | same | `NovaCanvasPipe()` |
| `OllamaPipe` | `TPipe-Ollama/` | `com.github.ten-trillion-triangles:TPipe-Ollama:<v>` | `OllamaPipe()` (line 31) |

## 3. The builder surface on `Pipe` (~70 chained setters return `this`)

Verified against `src/main/kotlin/Pipe/Pipe.kt`. Selected highlights (the full list is several hundred methods, but these are the day-one set):

```kotlin
.setPipeName("…")
.setProvider(ProviderName.ANTHROPIC)
.setModel("claude-sonnet-4-5")
.setSystemPrompt("…")
.setUserPrompt("…")
.setTemperature(0.7)
.setTopP(.9)
.setTopK(40)
.setMaxTokens(1024)
.setReasoning()                                 // three overloads: none / tokens / custom
.setJsonOutput(MyResult::class)                 // or setJsonOutput(json: String)
.setJsonInput(MyInput::class)
.enableStreaming()
.setStreamingCallback { token -> print(token) }
.enableCaching("default")
.setTokenBudget(TokenBudgetSettings().multiplyWindowSizeBy(2))
.setContextWindowSize(4096)
.enableHarnessMode()
.enableDeterministicGeneration(seed = 42)
.setLogitBias(mapOf(50256 to -100.0))
.setStopSequences(listOf("\n\nSTOP"))
.setReasoningPipe(otherPipe)
.setPreInvokeFunction  { content -> true }      // suspend
.setPreValidationFunction { ctx, content -> ctx }
.addPcpContext(PcpContext().apply { bindFunction("toolName", ::myFn) })
.applySystemPrompt()
.execute("prompt")                              // suspend → String
.execute(MultimodalContent("prompt"))           // suspend → MultimodalContent
```

## 4. Container ergonomics

| Container | Builder API | Scope DSL |
|---|---|---|
| `Pipeline` | `Pipeline().add(pipeA).add(pipeB)` | none |
| `Connector` | `Connector().add("k", pipeline).setDefaultPath("k")` | none |
| `MultiConnector` | `MultiConnector().add(connector).setMode(SEQUENTIAL)` | none |
| `Splitter` | `Splitter().addContent("k", content).addPipeline("k", pipeline)` | none |
| `Manifold` | `Manifold()` builder class | `manifold { worker("name") { pipeline { add(pipe) } } }` |
| `Junction` | `JunctionBuilder<Stage>()` (state machine) | `junction { moderator(...) participant(...) }` |
| `DistributionGrid` | `DistributionGridBuilder<Stage>()` | `distributionGrid { p2p { … } router(pipe) worker(pipe) }` |
| `PumpStation` | builder | `pumpStation { … }` |

All containers expose `execute(content)` and (where applicable) `runOnce()` / `runLoop()`.

## 5. MultimodalContent construction

```kotlin
MultimodalContent(text = "…")                    // primary constructor
  .addText("more")                              // chainable
  .addBinary(byteArray, mime = "image/png")     // chainable
  .addBinary(base64String, mime = "image/png")  // overload
```

Runtime control flags on the same instance:

```
content.terminate()           // halt pipeline cleanly (not an error)
content.jumpToPipe("name")    // branch
content.passPipeline          // skip current
content.repeatPipe            // redo current
content.clearJumpToPipe()     // cancel a pending jump
```

## 6. PCP tool binding from a script

```kotlin
import com.TTT.PipeContextProtocol.PcpContext
import com.TTT.PipeContextProtocol.bindFunction      // ext
import com.TTT.Pipe.DummyPipe
import com.TTT.PipeContextProtocol.bindNativeFunction // ext on Pipe

fun myTool(input: String): String = "tool-returned: $input"

val ctx = PcpContext().apply { bindFunction("my_tool", ::myTool) }
val pipe = DummyPipe()
  .apply { /* …config… */ }
  .bindNativeFunction("my_tool", ::myTool)            // alt: wire directly on Pipe
```

## 7. Reference: file sizes of the major source modules

```
src/main/kotlin/Pipe/Pipe.kt                          7,839 lines
src/main/kotlin/Pipe/MultimodalContent.kt             <— data class, see file
src/main/kotlin/Pipeline/Pipeline.kt                  1,873
src/main/kotlin/Pipeline/Manifold.kt                  2,260
src/main/kotlin/Pipeline/Junction.kt                  4,120
src/main/kotlin/Pipeline/DistributionGrid.kt          8,775
src/main/kotlin/Pipeline/Splitter.kt                    945
src/main/kotlin/Pipeline/Connector.kt                   408
src/main/kotlin/Pipeline/PumpStation.kt               4,465
src/main/kotlin/P2P/P2PRegistry.kt                    1,423
src/main/kotlin/Context/ContextWindow.kt              2,312
src/main/kotlin/Context/ContextBank.kt                1,737
src/main/kotlin/PipeContextProtocol/Pcp.kt              515
```

Large containers (DistributionGrid, PumpStation, Junction) are configuration-state complexity, not runtime complexity — they break down into staged builders that compose at runtime. For script work, focus on the public DSL surface first.
