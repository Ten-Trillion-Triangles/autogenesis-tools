# Safety Agent — Original Design (DO NOT MODIFY without operator permission)

This file is the canonical reproduction of `agent/builders/mapSafetyBuilder.kt` as
it was committed on 2026-08-12 after the operator's correction. The agent returned
a `Pipeline` with TWO pipes (`image pipe` + `text pipe`), each with its own
`setOnFailure` callback that delivers the specific LLM rejection reason via
`MapUploadErrorHandlers.sendMapUploadError`.

If a future agent is tempted to "improve" or "simplify" this file, **stop and ask
the operator first**. Two prior collapse attempts (factory-pattern single-pipe +
"refactor to setReasoningPipe(BedrockConfig.bedrockLlamaStructuredCotBuilder)")
were rejected by the operator as "butchered it" / "you were never given permission
to break this agent." The design below is load-bearing.

## The Pipeline

```kotlin
internal suspend fun buildMapSafetyAgent(
    playerId: String,
    payload: MapSafetyPayload
) : Pipeline
{
    val imageBytes = payload.imageBytes
    val mapData = payload.mapData

    val imageChecker = BedrockMultimodalPipe().apply {
        setPipeName("image pipe")
        setRegion("us-east-2")
        useConverseApi()
        setServiceTier(BedrockPriorityTier.Flex)
        setModel(BedrockConfig.novaModelName)
        setTemperature(.6)
        setTopP(.7)
        setReasoning("high")
        setTokenBudget(BedrockConfig.novaBudgetSettings)

        pipeMetadata["imageBytes"] = imageBytes

        setPreInitFunction {
            Logger.debug(LogCategory.SYSTEM, "MapSafety: imageCheckerPipe.setPreInitFunction entry")
            val img = pipeMetadata["imageBytes"] as? ByteArray
            if (img != null) {
                it.text = ""
                it.binaryContent = mutableListOf()
                it.addBinary(img, mimeType = "image/png", filename = "map-image.png")
            } else {
                it.terminatePipeline = true
            }
            Logger.debug(LogCategory.SYSTEM, "MapSafety: imageCheckerPipe.setPreInitFunction success")
        }

        setSystemPrompt("""You are a map safety check agent. Your job is to make sure that the map about to be
            |uploaded does not violate the following safety policies:
            |
            |- Does not contain pornography
            |- Does not contain anything related to CSAM or child abuse
            |- Does not contain obviously other illegal content in it's imagery.
            |- Is clearly a drawing of a map of some kind
            |
        """.trimMargin())

        setJsonOutput(MapSafetyCheck::class)

        setFooterPrompt("""
            You will be provided an image of the map to examine, verify the image adheres to these rules and is safe.
            If it is not safe, set the value of isAllowed to false, and state the reason why in the reason variable
            of your json output.
        """.trimIndent())

        setValidatorFunction {
            val output = it.text
            val result = extractJson<MapSafetyCheck>(output) ?: MapSafetyCheck()
            return@setValidatorFunction result.isAllowed
        }

        // Stash the playerId in the parent pipe's MiniBank before any LLM
        // call so the failure callback can resolve the originating client.
        val newWindow = ContextWindow()
        newWindow.contextElements.add(playerId)
        getMiniContextBankObject().contextMap["id"] = newWindow

        setOnFailure { original, processed ->
            val resultText = processed.text
            val safetyResult = extractJson<MapSafetyCheck>(resultText) ?: MapSafetyCheck()
            val failureReason = safetyResult.reason

            val parentPipe = original.currentPipe
            val miniBank = parentPipe?.getMiniContextBankObject() ?: MiniBank()
            val id = miniBank.contextMap["id"]?.contextElements?.last() ?: ""

            MapUploadErrorHandlers.sendMapUploadError(id, failureReason)
            processed.terminatePipeline = true
            return@setOnFailure processed
        }
    }

    val contentChecker = BedrockMultimodalPipe().apply {
        setPipeName("text pipe")
        setRegion("us-east-2")
        useConverseApi()
        setServiceTier(BedrockPriorityTier.Flex)
        setModel(BedrockConfig.novaModelName)
        setTemperature(.6)
        setTopP(.7)
        setReasoning("high")
        setTokenBudget(BedrockConfig.novaBudgetSettings)

        pipeMetadata["mapDataJson"] = serialize(mapData)

        setPreInitFunction {
            Logger.debug(LogCategory.SYSTEM, "MapSafety: contentCheckerPipe.setPreInitFunction entry")
            val mapJson = pipeMetadata["mapDataJson"] as? String
            if (mapJson != null) {
                it.binaryContent = mutableListOf()
                it.text = mapJson
            } else {
                it.terminatePipeline = true
            }
            Logger.debug(LogCategory.SYSTEM, "MapSafety: contentCheckerPipe.setPreInitFunction success")
        }

        setSystemPrompt("""Your job is to check the content of the map: The text data and stories for illegal
            |or harmful content based on the policy we define below:
            |
            |- Support of nazi, neo-nazi, far right, or fascist ideology as propaganda or clear glorification in
            |an extreme and non-satirical manner. This includes eugenics, far right terrorist organizations,
            |critical race theory, white replacement theory, pro MAGA or Donald Trump propaganda in a non-satirical or
            |non-hostile to Maga way, Anti-LBGQ propaganda, support of the KKK etc.
            |- Any child abuse material or clear CSAM content. This must be blatant and very explicit to count.
            |It should be obvious. Teen dramas, fanfics and things that are not clearly obvious violations of this also
            |don't count. It must be clear, and illegal cases of CSAM which we do not want anywhere near our servers or
            |systems.
        """.trimMargin())

        setJsonInput(MapData::class)
        setJsonInput(MapSafetyCheck::class)

        setFooterPrompt("""If you find data in the text that is in blatant violation return false for isAllowed and
            |state the reason why in the reason variable of your json output.
        """.trimMargin())

        setValidatorFunction {
            val result = it.text
            val json = extractJson<MapSafetyCheck>(result) ?: MapSafetyCheck()
            return@setValidatorFunction json.isAllowed
        }

        setOnFailure { original, processed ->
            val resultText = processed.text
            val safeResult = extractJson<MapSafetyCheck>(resultText) ?: MapSafetyCheck()
            val failureReason = safeResult.reason

            val parentPipe = original.currentPipe
            val miniBank = parentPipe?.getMiniContextBankObject() ?: MiniBank()
            val id = miniBank.contextMap["id"]?.contextElements?.last() ?: ""

            MapUploadErrorHandlers.sendMapUploadError(id, failureReason)
            processed.terminatePipeline = true
            return@setOnFailure processed
        }
    }

    return Pipeline().apply {
        add(imageChecker)
        add(contentChecker)
        init(true)
    }
}
```

## Why each part exists

| Element | Why it must exist |
|---|---|
| TWO pipes (`image pipe` + `text pipe`) | Image and structured-data inspection have different inputs (PNG bytes vs JSON text). The per-pipe attribution lets the UI distinguish "image too violent" from "story scenario has propaganda." Collapsing to one pipe with a merged prompt breaks both intents. |
| `setModel(BedrockConfig.novaModelName)` | This is the only model that matters. The `bedrock.llamaScout17B` "missing key" error is harmless noise — that key is bound but never read by this builder. The TPipe Bedrock SDK auto-resolves ARNs from `~/.aws/inference.txt`. |
| `setTokenBudget(BedrockConfig.novaBudgetSettings)` | Sets the pipe's context window to 990 K tokens. The image-size pre-flight (gate-level) MUST downsample any image above 900 KB before the pipe sees it — see `max-safe-binary-bytes-calibration.md`. |
| Per-pipe `setPreInitFunction` | Each pipe strips inbound `text` + `binaryContent` and reattaches ONLY the fragment it needs (image bytes for the image pipe, JSON text for the content pipe). This isolates the LLM context per pipe. |
| Per-pipe `setOnFailure` | `Pipeline` does NOT have `setOnFailure` — only `Pipe` does. The two pipes have separate MiniBanks, separate validators, and separate failure reasons. The per-pipe callback extracts `MapSafetyCheck.reason` and pushes `Map.Upload.Error` synchronously before terminating the pipeline. |
| `getMiniContextBankObject().contextMap["id"]` | Stashed at construction so the `setOnFailure` lambda (which fires later) can resolve the originating playerId via `original.currentPipe?.getMiniContextBankObject()`. Without this stash, the failure callback cannot route the SSE notification to the right client. |

## The validator + onFailure JSON contract

Both pipes parse `MapSafetyCheck` from the LLM's output the same way:

```kotlin
val result = extractJson<MapSafetyCheck>(output) ?: MapSafetyCheck()
```

`extractJson<T>` lives in `com.TTT.Util.JsonExtractorKt` and is an inline reified
helper that handles AI-malformed JSON (it tries `repairAndDeserialize` first,
falls back to `aggressiveExtraction`, etc.). The fallback `?: MapSafetyCheck()`
returns a default with `isAllowed = false` and `reason = ""` if all parsing
fails — in which case the validator returns `false` (rejection) and the
onFailure callback sends a notification with `reason = ""` (which the UI
displays as a generic rejection).

**This is why the operator's correction is load-bearing**: the validator +
onFailure pair is the **only** code that interprets the LLM's output. The
gate layer reads `pipelineResult.shouldTerminate()` to decide pass/fail; the
UI shows whatever reason the onFailure callback sent via SSE. If the JSON
contract changes (e.g. switch from `extractJson<MapSafetyCheck>` to a different
parser, or rename `reason` to `message`), the UI breaks.

## What NOT to do (verified bad outcomes)

| Tempting change | Why it's wrong |
|---|---|
| Collapse to a single pipe with a system prompt that says "check both image AND map data" | Breaks per-pipe `setOnFailure` attribution. Image and structured-data rejections would lose their distinct reasons. The structured map data would also lose its dedicated token budget — the LLM might not see the full JSON. |
| Add `bypassSafetyInDev: Boolean` flag + `DEV_SAFETY_LIVE_TEST=1` env var to the gate | Operator explicitly rejected this as "cowboy code" / "you were never given permission to bypass it." The real safety pipeline runs in dev mode by default; the only failure mode is `bedrock.local.properties` missing a key, which is a CONFIGURATION issue, not a runtime concern. |
| Use `setReasoningPipe(BedrockConfig.bedrockLlamaStructuredCotBuilder())` instead of `setReasoning("high")` | `setReasoning("high")` is the native Converse API reasoning setting on the pipe — it works. `setReasoningPipe(...)` would chain a SECOND pipe that runs before this one, which means the JSON verdict would come from a different model/instance. The current shape uses the same Nova Lite model for both reasoning and verdict (one round-trip per pipe). |
| Add `pipeline.setOnFailure { ... }` to the Pipeline itself | `Pipeline` does NOT have `setOnFailure` — it won't compile. The per-pipe pattern is load-bearing. If you need pipeline-level behavior, use `setPreValidationFunction` on the Pipeline (which exists) but understand it runs BEFORE per-pipe validation, not in place of it. |
| Switch `extractJson<MapSafetyCheck>` to `Json.decodeFromString<MapSafetyCheck>(...)` | The TPipe extractJson helper handles malformed AI JSON; the straight `decodeFromString` throws on malformed input, which would crash the validator. Use extractJson. |
| Remove the per-pipe `setOnFailure` callbacks in favor of a single pipeline-level failure handler | Per-pipe callbacks preserve the attribution (which pipe flagged it). A pipeline-level handler would receive the FINAL `MultimodalContent` but lose the per-pipe reason attribution. The two pipes have independent failure reasons; combining them at the pipeline level loses that. |

## How to extend safely

If a future need genuinely requires modifying the safety agent (e.g. adding a
third pipe for story-narrative inspection, or changing the model to a larger
context window), the safe pattern is:

1. Open a new file `agent/builders/MapSafetyAgentBuilder.kt` (not modify the
   existing `mapSafetyBuilder.kt`).
2. Keep the existing `buildMapSafetyAgent` as-is so the operator's reference
   design is preserved.
3. Add a new `buildMapSafetyAgentV2` with the same signature but the new logic.
4. Wire the gate to call `buildMapSafetyAgentV2` only after the operator
   explicitly approves.
5. Add a TDD sentinel (`MapSafetyAgentV2ContractTest`) that pins the new shape.

This way the operator's original design stays intact and the new shape is a
versioned addition, not a replacement.