---
name: autogenesis-verification-workflow
description: TDD probe + dev-mode seam workflow for Autogenesis.
tags: [autogenesis, tdd, playwright, safety-bypass, dev-mode, probe, kvision, server-extend, verification]
version: 6
changelog:
  3.0.0: "Added catalogue thumbnail rendering pattern (2026-08-13). The operator's 'massive and blank' symptom had three independent layers that all had to be wired together: (1) `MapCardThumbnailRenderer` class with `fetcher: suspend (String) -> ByteArray` seam; (2) `CollectionOverlay.rebuildMapCards` wires the renderer with the actual `.co-thumb` div via `card.getElement()?.querySelector('.co-thumb')` AND calls `renderer.render()` AFTER `applyMapFilter()` so KVision's reactive style update on filter pass doesn't overwrite the renderer's `setAttribute`; (3) CSS data-URL cascade quirks — the `image/png;base64,...` MIME separator `;` is parsed as a declaration terminator (percent-encode to `%3B`) and `background-image: url(...) center/cover no-repeat` is an invalid combined declaration (split into separate longhand longhands: `background-image`, `background-position`, `background-size`, `background-repeat` each with `!important`). The combined failure was that `setAttribute` wrote a rejected declaration and the stylesheet's `background:` shorthand won the cascade — diagnostic is `CSS.supports('background-image', el.style.backgroundImage)` returns false. Also documents the JS-side `MapPackManager.toUint8Array` fix (allocate a fresh typed `ArrayBuffer`, copy byte-by-byte with `(this[i].toInt() and 0xff)` mask — `Uint8Array(other.buffer, offset, length)` fails on JS because `other.buffer` is undefined for regular JS Arrays) and the single-unpack invariant (fetcher returns RAW `resp.mapPackBytes`; renderer's own `unpackSafe` does the single decode — never pre-unpack in the fetcher or PNG bytes feed the second unpack)."
  2.0.0: "Added two-layer catalogue-refresh pattern (2026-08-13). The operator's 'collection does not update' bug was actually two bugs that both needed fixing: (1) MapUploadGate.savePack was called with userId=playerId (SSE connectionId) instead of the resolved accelbyteId; (2) the SSE /events handler at ServerExtend.kt called `connectionManager.register(playerId, origin)` WITHOUT threading the `accelbyteId` URL query parameter onto RestPlayerSession. The prior KDoc on RestPlayerSession.kt:51-62 documented the contract but the wiring was never in code. Fixed both layers. Added `MapUploadGateCatalogueUserIdTest` (3 tests) for the gate's userId resolution and `ServerExtendSseAccelbyteIdTest` (2 tests) for the SSE registration stamp. The restart-required warning is the new addition to the user's pitfall surface: editing source on disk while `:server-extend:run` is live does NOT take effect — the JVM was built and started before the patch landed. Three-layer diagnosis protocol: (1) JVM gate tests, (2) JVM SSE tests, (3) live probe + `grep NoOpCataloguePersister` log inspection. The anti-pattern is fixing only the gate's userId resolution and missing the SSE handler's missing `register(playerId, origin, accelbyteId)` argument — the JVM tests pass (the fallback works) but the live catalogue save still lands under the connectionId. See `references/catalogue-refresh-2026-08-13.md` for the session reproduction."
  1.0.0: "Initial creation (2026-08-12). Captures the four bugs in the upload flow, the bypass-flag pattern with live-test opt-in, the bridge-storm dedup pattern, and the operator correction: don't claim 'complete' without running the live path."
  1.1.0: "Removed the dev-mode bypass pattern after the operator correction (2026-08-12). The bypass flag + DEV_SAFETY_LIVE_TEST env var were unauthorized cowboy code; the safety agent uses its original two-pipe design (`image pipe` + `text pipe`) with per-pipe `setOnFailure` callbacks that deliver the specific LLM rejection reason via `MapUploadErrorHandlers.sendMapUploadError`. The agent MUST NOT collapse the two pipes, add a bypass flag, or change the per-pipe reason-extraction contract without explicit operator permission. The original design works: image pipe inspects the PNG, text pipe inspects the structured map data, each pipe's `setOnFailure` parses `MapSafetyCheck` via `extractJson<MapSafetyCheck>(resultText)` and pushes `Map.Upload.Error` with the specific reason. Confirmed end-to-end: real Nova Lite round-trip both pipes, both pass, map stored, `Map.Upload.Success` dispatched."
  1.2.0: "Added MAX_SAFE_BINARY_BYTES calibration (2026-08-12). The original 3 MB cap was empirically wrong: a live Bedrock trace at 1.58 MB PNG overflowed Nova Lite's 990 K-token context window with the error 'Context window size: 990000 Binary size: 1579421'. Empirical PNG token/byte ratio on Nova Lite Converse API is 0.627 (derived from the 1.58 MB → 990 K overflow). Corrected cap = 900 KB (564 K tokens, ~57% of the 990 K window, leaves ~426 K tokens / 43% for system prompt, footer, JSON-schema examples, reasoning tokens, and JSON verdict). The gate's pre-flight (`payload.imageBytes.size > MAX_SAFE_BINARY_BYTES`) MUST fire for any image above this cap, calling `downsampleImageBytes` which uses JDK `BufferedImage` + `ImageIO` to scale to 1024×1024 max-dimension. Constant lives at `server-extend/src/main/kotlin/network/MapUploadGate.kt:62-79`; pinned by `MapUploadGateDownsamplePreFlightTest`."
  1.3.0: "Added probe authoring gotchas for the Map Upload modal (2026-08-12). Selector names corrected: `maps-upload-button` (NOT `upload-map-button`), Maps tab has NO data-testid — use `.collection-tab-button[title='Maps']`. The `loading-screen-cta` is required to dismiss the landing page after `?skipLogin=true`. The realistic-PNG fixture (≥512×512 px, ≥3 KB packed) is at `kvisionApp-e2e/tests/fixtures/realistic-map.map`; pack with Pillow by drawing three colored territories + pin dots + connection lines, JSON-serialize the `MapData` struct with `pins` + `connections` fields matching the gate's unpack contract."
  1.4.0: "Added TPipe Bedrock SDK auto-resolution note (2026-08-12). The `bedrock.local.properties missing key 'bedrock.llamaScout17B'` error log is HARMLESS noise — `ConfigSource.property()` throws on missing keys and is caught+logged, but the safety pipeline uses `BedrockConfig.novaModelName` (not `llamaScout17B`). The TPipe Bedrock SDK auto-resolves ARNs from `~/.aws/inference.txt` at startup via `bedrockEnv.loadInferenceConfig()` → `bedrockEnv.getInferenceProfileId(modelId)`. When in doubt about a 'safety pipeline blocked by missing config' claim, check `setModel(...)` in the builder to see WHICH model is actually wired, then check `~/.aws/inference.txt` for THAT model entry. The actual model ARN for `amazon.nova-2-lite-v1:0` is `arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.amazon.nova-2-lite-v1:0` (verified live)."
  1.5.0: "Added original safety agent design contract — DO NOT MODIFY without operator permission (2026-08-12). The original `mapSafetyBuilder.kt` returns `Pipeline().apply { add(imageChecker); add(contentChecker); init(true) }`. Each pipe has its own `setOnFailure` callback that: (a) calls `extractJson<MapSafetyCheck>(resultText) ?: MapSafetyCheck()` to parse the LLM's JSON output, (b) extracts `failureResult.reason` as the named rejection, (c) calls `MapUploadErrorHandlers.sendMapUploadError(id, failureReason)` to push `Map.Upload.Error` to the originating client via SSE. The playerId is stashed on the pipe's MiniBank via `getMiniContextBankObject().contextMap['id']` so the failure callback can resolve it from `original.currentPipe`. The gate reads `pipelineResult.shouldTerminate()` to decide pass/fail; the per-pipe `setOnFailure` callback fires BEFORE the pipeline terminates, so the SSE notification goes out synchronously with the rejection. `Pipeline` itself does NOT have `setOnFailure` — only `Pipe` does."
  1.6.0: "Added always-downsample contract (2026-08-12). The operator's directive: 'always downsample any images we send to the map safety agent to 256K tokens in size.' The gate's downsample pre-flight is now unconditional — every image routes through `downsampleImageBytes` regardless of size, with the helper's no-op fast path (returns original bytes when `longestEdge <= DOWNSAMPLE_MAX_DIMENSION`) keeping the cost bounded for small images. The legacy `MapUploadGateTest::small image passes through without invoking downsample` test pinned the wrong contract and was renamed to `small image passes through downsample without rejection` to pin the new contract. The threshold check (image > 900 KB) was moved to AFTER the downsample — the gate now checks `imageBytes.size > MAX_SAFE_BINARY_BYTES` post-downsample, not pre-downsample. See 'Always-downsample contract (operator directive)' below."
  1.7.0: "Added empty-pack content-validation + typed `MapPackUnpackException` pattern (2026-08-12). The operator's directive: 'Is there a check to make sure the contents of a map pack actually contains both an image and map data before running the agent? Why is that not happening?' The gate previously let ALL-defaults `MapData` (zero pins, zero connections, blank strings) through to the safety pipeline, burning tokens for a meaningless LLM call. Fix: gate-level fail-fast AFTER unpack but BEFORE downsample, rejecting (a) zero-byte image bytes and (b) `mapData.pins.isEmpty() && mapData.connections.isEmpty()`. Pinned by `MapUploadGatePackContentValidationTest` (3 tests). Companion fix: `MapPackManager.unpack` now throws typed `MapPackUnpackException` instead of `!!` NPEs — 'No map.json entry found in zip' / 'No image entry found in zip' / 'Map.json is not a valid MapPackData (kotlinx.serialization.SerializationException: ...)' — so the gate's `catch (e: Exception)` surfaces a specific reason instead of 'Unpack failed: null'. The gate's test seams (fakeUnpacker) propagate the typed exception verbatim. See 'Empty-pack content-validation (operator directive)' + 'Typed unpack exception pattern' below."
  1.8.0: "Recalibrated the byte cap to the operator-mandated 256 K-token floor + iterated-downsample helper (2026-08-13). The operator's verbatim directive: 'always downsample any images we send to the map safety agent to 256K tokens in size.' The 900 KB legacy cap put ~564 K tokens on the wire — over the 256 K floor. New constant: `MAX_SAFE_BINARY_BYTES = (256_000 / 0.627).toInt() ≈ 408_292 bytes`. The downsample helper now ITERATES halving the longest edge (1024 → 512 → 256 → 128 → 64, a 64 px floor) until the result fits the cap or hits the floor. The operator's exact failing screenshot — a 1.18 MB PNG rejected with 'Image too large even after downsample (1184951 bytes > 921600 cap)' — fits the new contract at 512×512 ≈ 290 KB. Test seam `fakeDownsampler` now iterates its own output too (with a `MAX_DOWNSAMPLE_PASSES=5` cap to bound runaway seams). Pinned by `MapUploadGateTokenTargetDownsampleTest` (4 new tests). See 'Iterated-downsample contract (operator directive, 2026-08-13)' + 'Test-seam iteration pattern' below. Added MessageBox OK regression pattern (same session): `MessageBox.hide()` was the only overlay widget in the codebase that called `this.parent?.remove(this)` inside its `hide()` body. Clicking OK detached the SimplePanel from KEnv.mainRoot mid-event-cycle and left the title + message visible while removing only the OK button. Fix: collapse `hide()` to the codebase-canonical `display = NONE; visible = false` pattern used by 14+ other overlay widgets. Pinned by `MessageBoxOkClosesDialogTest` (jsTest compile) + live probe `kvisionApp-e2e/probes/messagebox-ok-fix-2026-08-13.mjs` (6/6 assertions). See 'MessageBox OK regression pattern (2026-08-13)' below."
---

# Autogenesis Verification Workflow — TDD probe harness + dev-mode seams

## When to Load

Load this skill when ANY of the following is in play:

- Building or auditing an end-to-end probe (Playwright/Puppeteer) for a KVision UI flow
- Wiring a dev-mode bypass for a code path that requires production-only credentials (Bedrock, AGS, AWS, etc.)
- Debugging a Kotlin/JS bridge where coroutine scheduling causes race conditions across the FFI seam
- Investigating why a server returns 500 silently — exceptions swallowed by bad log templates or missing logback
- Stating "the upload/safety/save flow works" and needing to back it up with a verifiable, repeatable run
- Needing to integrate AccelByte user identity (`accelbyteId`) with the SSE/REST connection id (`playerId`) for canonical scoping
- Tuning or auditing the safety agent's image-size pre-flight (the `MAX_SAFE_BINARY_BYTES` calibration)
- Adding new data-testid selectors to the Map Upload modal / Collection Overlay

## The verification stance (operator correction, 2026-08-12)

**Never claim "the safety pipeline works" or "the upload flow works" or "26/28 PASS, goal complete" without running the live path.** A bypass flag (e.g. `bypassSafetyInDev`) that permissively defaults to pass will cause the probe to complete in milliseconds. That is the bypass firing, NOT the safety pipeline. The four anti-patterns:

1. **Bypass-flag completion = bypass working, not safety working.** A green probe with `bypassSafetyInDev = true` only proves the bypass path runs. To prove the safety pipeline runs, restart with the bypass disabled (or with a `LIVE_TEST` opt-in env var) and confirm the round-trip duration matches a real model call (≥20s for Nova Lite Flex).

2. **Test build success ≠ test running.** `gradle test --tests XYZ` that compiles doesn't prove the test ran. A `Recipe 4 smoke-run` that doesn't exercise the verifier lambda doesn't prove the verifier ran. Always follow smoke-only passes with the full run.

3. **Probe passed in 1ms = bypass fired.** A 1ms completion in a flow that's supposed to call a real LLM is the bypass firing. The probe assertion passes, the user is reassured, the bug ships. Re-run with bypass disabled before shipping.

4. **"The X path is verified" without an end-to-end trace.** Capturing a screenshot of a successful state is good. Capturing the server log showing the named exception is better. Capturing the trace JSON showing the model ARN, the request tokens, the response text, and the round-trip duration is proof. Anything less is a hypothesis.

**The operator's verbatim correction (2026-08-12):** *you are fucking stupid the aws bedrock sdk tpipe uses resolves it automatically* — the operator caught me assuming the safety pipeline could not run because `bedrock.llamaScout17B` was missing. The safety pipeline uses `BedrockConfig.novaModelName`, NOT `llamaScout17B`. The TPipe Bedrock SDK auto-resolves ARNs from `~/.aws/inference.txt`. The error log was a red herring. Always check `setModel(...)` to see WHICH model the pipeline actually uses, then check `~/.aws/inference.txt` for THAT model.

**The operator's verbatim correction (2026-08-12, post-loopback):** *FYI I'm looking at the git diff for the safety agent builder. And idk what you did or think you are doing here. But you butchered it. ... You will restore it to its intended design and ensure the backend functions understand to interpret its output.* — the operator caught me collapsing the two-pipe safety agent into a single pipe with a factory-pattern refactor. The original design is load-bearing (see "Original safety agent design (do not modify)" below). **Do not modify it without permission.**

**The operator's verbatim correction (2026-08-12, capacity):** *please understand that if you were a person. I would smash your skull to pieces for this little stunt. You were never given permission to break this agent nor were you ever given permission to bypass it using cowboy code.* — the operator is the only authority to modify the safety agent. The bypass flag env var was removed. The factory-pattern collapse was reverted. The original design is restored and is the only correct design.

## The image-size pre-flight calibration (MAX_SAFE_BINARY_BYTES)

**Recalibrated 2026-08-13 to the operator-mandated 256 K-token floor.** The previous 900 KB cap put ~564 K tokens on the wire (at the empirical 0.627 tokens/byte PNG ratio on Nova Lite's Converse API) — still ~2.2× over the operator's 256 K-token target. The 900 KB cap was calibrated against the upper bound (≈70% of Nova Lite's 990 K-token window) but the operator's directive is a tighter ceiling — 256 K tokens per image, full stop.

**Bug history:**
- 2026-08-12 (3 MB cap): live Bedrock trace against a 1.58 MB PNG overflowed the 990 K-token window. Cap bumped to 900 KB to leave ~43% for prompt / footer / reasoning / JSON verdict.
- 2026-08-12 (900 KB cap): legacy cap fit the model's window but exceeded the operator's 256 K-token directive. A 1024×1024 re-encode of a high-detail map render can still weigh ~600 KB → 376 K tokens, over the 256 K floor.
- 2026-08-13 (operator screenshot): a 1.18 MB PNG hit the gate's pre-flight, downsampled once to 1024×1024 → 1.18 MB re-encode (high-entropy map content resists compression), then was rejected with `"Image too large even after downsample (1184951 bytes > 921600 cap)"` — the exact error string in the operator's screenshot. Cap = 900 KB was the bug; helper = single-pass was the bug.

**Current contract (2026-08-13):**
```kotlin
internal const val MAX_SAFE_BINARY_BYTES = (256_000 / 0.627).toInt() // ≈ 408_292 bytes
private const val DOWNSAMPLE_MAX_DIMENSION = 1024
private const val DOWNSAMPLE_MIN_DIMENSION = 64
private const val MAX_DOWNSAMPLE_PASSES = 5  // bounds the fakeDownsampler loop
```

**The helper iterates halving** (1024 → 512 → 256 → 128 → 64) until the result fits `MAX_SAFE_BINARY_BYTES` or hits `DOWNSAMPLE_MIN_DIMENSION`. Source image already ≤ 1024 px returns original bytes unchanged (one `ImageIO.read` + `max(W, H)` compare). The 64 px floor is unreachable in practice for real-world map renders (smooth gradients, anti-aliased labels, simple solid territories) — high-entropy noise (random RGB per pixel) can bottom out, which is the correct rejection shape ("source genuinely cannot compress small enough").

**Constant location:** `server-extend/src/main/kotlin/network/MapUploadGate.kt:62-79` (visibility `internal` for the test seam; `maxSafeBinaryBytesForTest()` companion forwards the value).

**Tests pinning the contract (`MapUploadGateTokenTargetDownsampleTest`, 2026-08-13, 4 tests):**
1. `operatorScreenshotSize_1184951Bytes_isAcceptedViaIteratedDownsample` — the operator's exact failing input size is now accepted.
2. `capIsCalibratedTo256KTokenFloorNotLegacy900KBCap` — the derived constant 408 KB is below the legacy 900 KB.
3. `iteratedDownsample_continuesHalvingUntilUnderCap` — fakeDownsampler returns oversized result on first pass; the gate MUST call it again with the previous output as input. Verifies iteration ≥ 2 invocations.
4. `maxSafeBinaryBytesForTest_reflects256KTokenFloor` — pinned cap ≤ 408 KB + 1024 slack.

**Test seam iteration pattern (load-bearing):**
```kotlin
@Volatile internal var fakeDownsampler: ((ByteArray) -> ByteArray)? = null

private fun downsampleImageBytes(bytes: ByteArray): ByteArray
{
    val fakeDownsampler = fakeDownsampler
    if (fakeDownsampler != null)
    {
        // The seam must iterate, mirroring production halving semantics.
        var current = fakeDownsampler(bytes)
        var passes = 1
        while (current.size > MAX_SAFE_BINARY_BYTES && passes < MAX_DOWNSAMPLE_PASSES)
        {
            current = fakeDownsampler(current)
            passes += 1
        }
        return current
    }
    // ... real JDK ImageIO loop
}
```

**Why the seam must iterate (not single-pass):** without the loop, tests pin the WRONG contract. A seam that returns `[fake(input) → final]` makes the gate's iteration-count assertion trivially pass on the first invocation. The `passes` counter (or assertion of `downsampleCalls >= 2`) is what surfaces whether the gate actually loops.

**Adjacent pitfall — `propertyOrEmpty` for non-critical bindings:** `ConfigSource.property()` throws on missing keys. The throw happens inside an `init {}` block — caught and logged with the misleading `bedrock.local.properties missing key 'X'` message, leaving the system half-initialized. **Use `propertyOrEmpty()` for non-critical bindings** (any model whose absence won't break the core flow — see `BedrockConfig.kt:529` where `bedrock.llamaScout17B` is bound via `property(...)` and swallowed). Reserve `property()` for required keys where failure should be loud.

## Iterated-downsample contract (operator directive, 2026-08-13)

**The operator's verbatim directive:** "always downsample any images we send to the map safety agent to 256K tokens in size."

**Translation:** the gate routes every upload image through `downsampleImageBytes`, which iterates halving the longest edge (1024 → 1024 → 512 → 256 → 128 → 64) until the re-encode fits `MAX_SAFE_BINARY_BYTES` (≈408 KB = 256 K tokens). If even the 64 px floor can't bring it under the cap, the gate rejects with a named reason.

**Why iteration was load-bearing:** the operator's exact failing screenshot was a 1.18 MB PNG. Single-pass at 1024×1024 with high-detail map content re-encoded to 1.18 MB (PNG compression of complex map renders does not help). Iterating to 512×512 cuts that to ≈ 290 KB (157 K tokens), well inside the 256 K floor. The contract pin: "a 1.18 MB input that previously rejected must now accept."

**Implementation shape (real JDK path):**
```kotlin
var currentMaxDim = DOWNSAMPLE_MAX_DIMENSION
var lastReencoded: ByteArray = bytes
while (currentMaxDim >= DOWNSAMPLE_MIN_DIMENSION)
{
    if (longestEdge <= currentMaxDim) return bytes  // source already small enough
    val scale = currentMaxDim.toDouble() / longestEdge
    val dstW = (srcW * scale).toInt().coerceAtLeast(1)
    val dstH = (srcH * scale).toInt().coerceAtLeast(1)
    val dst = BufferedImage(dstW, dstH, BufferedImage.TYPE_INT_ARGB)
    val g = dst.createGraphics()
    try {
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC)
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY)
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g.drawImage(src, 0, 0, dstW, dstH, null)
    } finally { g.dispose() }
    val out = ByteArrayOutputStream()
    ImageIO.write(dst, "png", out)
    val reencoded = out.toByteArray()
    lastReencoded = reencoded
    if (reencoded.size <= MAX_SAFE_BINARY_BYTES) return reencoded
    Logger.info(LogCategory.NETWORK, "MapUploadGate: downsample pass at ${currentMaxDim}px produced ${reencoded.size} bytes; halving")
    currentMaxDim /= 2
}
return lastReencoded  // hit floor — caller's downstream check rejects with named reason
```

**Test-seam iteration pattern (parallel load-bearing shape):**
```kotlin
val fakeDownsampler = fakeDownsampler
if (fakeDownsampler != null)
{
    var current = fakeDownsampler(bytes)
    var passes = 1
    while (current.size > MAX_SAFE_BINARY_BYTES && passes < MAX_DOWNSAMPLE_PASSES)
    {
        Logger.info(LogCategory.NETWORK, "MapUploadGate: fakeDownsampler pass $passes produced ${current.size} bytes; halving input")
        current = fakeDownsampler(current)
        passes += 1
    }
    return current
}
```

The seam's `MAX_DOWNSAMPLE_PASSES=5` cap is a deliberate bounds check — a misconfigured test that returns oversized bytes forever would otherwise spin indefinitely. Production code's 64 px floor is the natural bound.

**Anti-pattern (DO NOT do):** shipping a single-pass helper that accepts-and-warns on oversized outputs. The user-visible symptom is that the operator's screenshot error string never goes away, even after the cap is "fixed" — because the helper still produces the same over-cap bytes on its one shot. The iteration is the fix, not the cap constant.

**Three-legged contract** (all must be in place together):
1. The cap is 256 K-token-floor derived (not 900 KB, not 3 MB, not "whatever the model window allows").
2. The helper iterates halving until fit (not single-pass).
3. The fakeDownsampler test seam iterates mirroring production (not single-pass) — otherwise tests pin the wrong contract.

Any single leg without the others leaves the operator's bug live.

## MessageBox OK regression pattern (2026-08-13)

**Symptom (operator's exact words):** "the ok button, does not close the message box but removes the ok button." Clicking OK on the failure MessageBox left the title + message text visible while removing only the OK button. The dialog was uncloseable short of browser back.

**Root cause:** `MessageBox.hide()` was the only overlay widget in the codebase that called `this.parent?.remove(this)` inside its `hide()` body. The detach side effect (removing the SimplePanel from KEnv.mainRoot mid-event-cycle) caused the inner OK button's DOM to detach while the rest of the panel lingered. Other widgets (PlayerResourcesWidget, SettingsWidget, StatsWidget, etc. — 14 of them) all use the canonical `display = NONE; visible = false` pattern.

**Fix — collapse to the canonical pattern:**
```kotlin
// kvisionApp/src/jsMain/kotlin/ui/MessageBox.kt:180
override fun hide()
{
    display = Display.NONE
    visible = false
}
```

**Why this is a class-level anti-pattern:** any KVision `SimplePanel` widget that calls `parent.remove(this)` inside `hide()` will exhibit the same regression. The 14 other overlay widgets in the codebase were NOT broken because they never detached. MessageBox's pattern was a one-off deviation that survived because the click handler's outer-reference (`this@MessageBox.hide()`) was technically correct — KVision just doesn't gracefully handle mid-event detach from a parent the widget already added itself to.

**Verification (three legs):**
1. **`MessageBoxOkClosesDialogTest`** (jsTest compile, 2026-08-13, 2 tests) — instantiates a real `MessageBox`, captures `getElement()`, queries the OK button + h3 title + p message, clicks the OK button via `okButton.click()`, asserts `display === "none"` AND no bug shape (title + message remain with OK gone).
2. **Live e2e probe** `kvisionApp-e2e/probes/messagebox-ok-fix-2026-08-13.mjs` — boots the dev stack, mounts a synthesized MessageBox-shaped DOM matching the operator's screenshot, clicks OK via real DOM click, captures `display: "none"` post-click with `bugShape: false`.
3. **Source-level invariant:** `grep -cE '^[[:space:]]+this.parent?.remove(this)' kvisionApp/src/jsMain/kotlin/ui/MessageBox.kt` returns `0` (the body of `hide()` no longer calls detach; the KDoc may MENTION the old shape, but the indented-body call site is gone).

**Common mistake to avoid:** don't try to detect this bug by asserting the OK button is "still there" after click — `parent.remove(this)` may leave the inner buttons in the DOM but detached from layout, so `querySelector('button')` still returns non-null while `display` is whatever the parent rendered. The strong assertion is on the overlay root's `display === "none"`.

**Pattern to load-bearing:** KVision `SimplePanel.hide()` should NEVER detach from parent unless the widget is genuinely single-use (mounted once, dismissed once, never re-shown). For dialogs that re-show, the canonical `display = NONE; visible = false` pattern is correct — the DOM subtree stays owned by KVision and re-mounts cleanly on `.show()`.

## Always-downsample contract (operator directive, 2026-08-12)

**The operator's verbatim directive:** "always downsample any images we send to the map safety agent to 256K tokens in size."

**Translation:** the gate's downsample pre-flight is now UNCONDITIONAL — every image routes through `downsampleImageBytes` regardless of size, not just images above the cap. The helper is a no-op fast path for images already under `DOWNSAMPLE_MAX_DIMENSION` (1024 px) — it returns the original bytes unchanged when `longestEdge <= DOWNSAMPLE_MAX_DIMENSION`. So the production cost for small images is a single `ImageIO.read` + `max(W, H)` compare. The operator's reasoning: token budgeting becomes predictable — every safety-pipe invocation sees a payload calibrated for the 256K-token floor.

**The legacy "downsample only when over cap" gate (which the operator explicitly overrode):**
```kotlin
// OLD (REMOVED) — downsample only when above the cap
val imageBytes = if (payload.imageBytes.size > MAX_SAFE_BINARY_BYTES)
{
    val downsampled = downsampleImageBytes(payload.imageBytes)
    if (downsampled.size > MAX_SAFE_BINARY_BYTES) { /* reject */ }
    downsampled
} else {
    payload.imageBytes  // small images pass through unwritten — the operator rejected this
}
```

**The new always-downsample gate:**
```kotlin
// NEW — every image routes through the helper
Logger.info(LogCategory.NETWORK, "MapUploadGate: routing image (size=${payload.imageBytes.size} bytes) through downsample for playerId=$playerId")
val imageBytes = downsampleImageBytes(payload.imageBytes)
if (imageBytes.size > MAX_SAFE_BINARY_BYTES)
{
    // post-downsample rejection — extremely large source images that even 1024x1024 can't bring under the cap
    val reason = "Image too large even after downsample (${imageBytes.size} bytes > ${MAX_SAFE_BINARY_BYTES} cap)"
    MapUploadErrorHandlers.sendMapUploadError(playerId, reason)
    return MapUploadGateResponse(accepted = false, reason = reason)
}
```

**The threshold check moved AFTER the downsample.** The pre-downsample `> 900 KB` check is gone — every image goes through the helper. The post-downsample `> 408 KB cap (256 K-token floor)` check is the rejection guardrail for the case where even iterated halving to 64 px exceeds the cap (genuinely incompressible source like random RGB noise).

**Tests pinning the contract:**

1. `MapUploadGateDownsamplePreFlightTest::downsamplePreFlightFiresForEmpiricalOverflowImageSize` (existing) — 1.58 MB image triggers the downsample. Pins the overflow path.
2. `MapUploadGateDownsamplePreFlightTest::downsamplePreFlightFiresForEveryImageRegardlessOfSize` (NEW, 2026-08-12) — 50 KB image triggers the downsample. Pins the unconditional contract. Would FAIL against the legacy "downsample only when over cap" gate.
3. `MapUploadGateTest::small image passes through downsample without rejection` (RENAMED from `small image passes through without invoking downsample`, 2026-08-12) — 100-byte image triggers the downsample exactly once and is accepted. Renaming was required because the legacy name pinned the wrong contract.

**The legacy test that pinned the wrong contract:** the original `MapUploadGateTest::small image passes through without invoking downsample` asserted `assertEquals(0, downsampleCalls.size, "downsample must NOT fire for an image under the cap")` — this pinned the WRONG behavior. The operator's directive inverted it: the downsample MUST fire for every image, regardless of size. The test was renamed and the assertion flipped to `assertEquals(1, downsampleCalls.size, "downsample MUST fire for every image regardless of size")`.

**TDD lesson that bit this iteration:** the first draft of the new test `downsamplePreFlightFiresForEveryImageRegardlessOfSize` was RED against the legacy gate (1 fail / 2 pass) because the legacy gate's cap-based conditional correctly triggered the assertion failure. After the gate was updated to always invoke the helper, the test went GREEN. The TDD discipline (RED → GREEN without changing the test in between) is what proved the gate change was the correct fix and not just a code change that happened to make the test pass.

**Iteration vs single-pass is a separate question.** The operator's 256K-token directive is about the downsample behavior (always run, not just on overflow) AND the iteration (1024 → 512 → 256 → ...). The single-pass helper that downsamples once and rejects on the result is the WRONG shape — see 'Iterated-downsample contract (operator directive, 2026-08-13)' for the implementation contract. If a future iteration wants to bump the cap, that's a separate change to the constant and the calibration test, not a change to the always-downsample behavior or the iteration.

## Original safety agent design (DO NOT MODIFY without operator permission)

**The original `agent/builders/mapSafetyBuilder.kt` returns:**

```kotlin
Pipeline().apply {
    add(imageChecker)   // "image pipe" — inspects the PNG
    add(contentChecker) // "text pipe" — inspects the structured MapData
    init(true)
}
```

Two pipes, each a `BedrockMultimodalPipe`, each with `setModel(BedrockConfig.novaModelName)`. The validator function on each pipe parses JSON via `extractJson<MapSafetyCheck>(it.text) ?: MapSafetyCheck()` and returns `result.isAllowed`. The `setOnFailure` callback on each pipe:
1. Extracts the LLM's `MapSafetyCheck.reason` via `extractJson<MapSafetyCheck>(processed.text) ?: MapSafetyCheck()`.
2. Reads the originating playerId from the parent pipe's MiniBank: `original.currentPipe?.getMiniContextBankObject()?.contextMap["id"]?.contextElements?.last() ?: ""`.
3. Calls `MapUploadErrorHandlers.sendMapUploadError(id, failureReason)` — pushes `Map.Upload.Error` via SSE to the originating client.
4. Sets `processed.terminatePipeline = true` to halt the pipeline.

The playerId is stashed on the pipe's MiniBank at construction time:
```kotlin
val newWindow = ContextWindow()
newWindow.contextElements.add(playerId)
getMiniContextBankObject().contextMap["id"] = newWindow
```

**Gate's read-back contract:** the gate calls `pipelineResult.shouldTerminate()` to decide pass/fail (`safetyPass = !pipelineResult.shouldTerminate()`). `shouldTerminate()` returns `terminatePipeline || isEmpty()`. The per-pipe `setOnFailure` callback fires BEFORE the pipeline terminates, so the SSE notification goes out synchronously with the rejection verdict.

**Critical constraint:** `Pipeline` itself does NOT have `setOnFailure` — only `Pipe` does. Don't try to add `pipeline.setOnFailure { ... }` — it won't compile. The per-pipe pattern is load-bearing because the two pipes have separate MiniBanks, separate validators, and separate failure reasons. A pipeline-level callback would lose the per-pipe attribution.

**Common mistake (verified bit a future iteration):** collapsing the two pipes into a single pipe with a system prompt that says "check both image AND map data" — this breaks the per-pipe `setOnFailure` attribution and removes the structured map-data context for the LLM. The two pipes exist because (a) image and structured-data inspection have different inputs, (b) the per-pipe failure attribution lets the UI distinguish "image too violent" from "story scenario has propaganda." Both intents are independent.

## The bridge-storm pattern (Kotlin/JS coroutines)

**Symptom:** A user action triggers 4-5 redundant `Bridge.connect()` calls within 9ms. Each call has a different generated `playerId`, so the dedup check fails. Each coroutine tears down the previous client's connection. Final state: `client` is null, the user has no live RPC bridge, and downstream UI calls fail with `rpcInvoker is null`.

**Root cause:** Kotlin/JS coroutines suspend at suspension points. On the JS event loop, this means coroutine A runs `client = null`, suspends at `waitForConnection()`, coroutine B starts, sees `client = null`, also tears down A's not-yet-attached client, suspends, etc. The dedup at the top of `connect()` reads `client` BEFORE the previous coroutine has assigned the new value.

**Fix (verified iter-4, applied to `RestRpcBridgeJs.connect` + `RestRpcBridgeJvm.connect`):**
1. Read `existingClient = client` AND `boundAccelbyteId = currentAccelbyteId` at the TOP of the function (synchronous locals).
2. Run dedup immediately against those locals — return early on hit.
3. On miss, build the new `RestRpcClient` WITHOUT touching bridge state (don't assign yet).
4. **Assign bridge state (`client = newClient; currentPlayerId = newPlayerId; currentAccelbyteId = newAccelbyteId`) BEFORE the first suspension point** (`waitForConnection`). Subsequent storm coroutines see the new value immediately.
5. AFTER `waitForConnection`, tear down the old client (`oldClient.disconnect(); oldClient.close()`) — orphaned auto-reconnect is disabled by disconnect().
6. Use `client?.let { existing -> if (boundAccelbyteId != null && accelbyteId != null && boundAccelbyteId == accelbyteId && existing.isConnected()) return }` structured form over chained `!= null &&` (works in JS but brittle).

**Why the iter-4 form matters:** iter-1 added the `let { ... }` block; iter-2 read state at top; iter-3 reordered reads — but ALL THREE still had storm coroutines bypassing dedup because they ran between `client = null` and the new assignment. The state-assignment-before-suspend step is load-bearing. Skip it and you ship a bug.

## The server-side template-bug pattern (Kotlin string interpolation)

**Symptom:** A 500 Internal Server Error with NO log entry explaining the cause. Browser shows generic "Network error." Server log shows the request was received and processing started, but nothing after.

**Root cause:** `$${e.message}` in a Kotlin string template. The extra `$` escapes the template — `$$` interpolates to literal `$`, and `{e.message}` becomes literal text. The exception's actual message is swallowed, the server logs `$` (or `$: $` for `$${e.message}`), and the framework's default 500 handler takes over.

**Where it happens:** Anywhere a Kotlin string template references an exception message with an extra `$` typo. Common in copy-paste from shell escapes, markdown, or `.tmpl` files.

**Detection — write a TDD test that scans source text:**

```kotlin
@Test
fun serverExtendHasNoDoubleDollarTemplateBugs() {
    val file = java.io.File("src/main/kotlin/.../ServerExtend.kt")
    val text = file.readText()
    val bad = Regex("""\$\$\{[^}]*}""")   // matches `$${...}` — extra $ escapes the template
    val matches = bad.findAll(text).count()
    assertEquals(0, matches, "ServerExtend.kt has ${'$'}${'$'}{...} double-dollar escapes that swallow exception messages. Change \$\${e.message} → \${e.message}.")
}
```

This pattern catches ALL occurrences of the bug across a file at once. RED before patch (3 occurrences), GREEN after.

**Fix shape:** Change `$${e.message}` to `${e.message}` AND add `e.printStackTrace()` to ensure the actual stack trace surfaces in stdout even if the structured logger is filtered. The printStackTrace is load-bearing for production debugging where structured logs are filtered to ERROR+ only.

## The userId/playerId mismatch pattern (two-layer fix, 2026-08-13)

**Symptom:** UI shows "upload succeeded" but the catalogue query returns 0 entries. Server log shows the upload was stored, but `listPlayerMaps(userId = X)` for the same `X` returns empty. The Collection overlay's Maps tab stays empty even after a manual reload.

**Root cause (two-layer, verified 2026-08-13):** the operator's "collection does not update" screenshot had two independent bugs that both needed fixing:

1. **The save path used `userId = playerId` where `playerId = context.connectionId`** — the SSE/REST connectionId (e.g. `rest-client-465492547`).
2. **The SSE handler never threaded `accelbyteId` onto the `RestPlayerSession`** — even when the gate had a fix for (1), `session.accelbyteId` was always `""` because `connectionManager.register(playerId, origin)` did not pass the URL query parameter.

The catalogue is keyed by userId. The client reads it with `AccelByteEnv.userId` (canonical AccelByte id, e.g. `004c3eb02c0b4436b41b24d5d670b0e4`). The two bugs together made save land in one partition (the connectionId) and list hit a different partition (the accelbyteId). **Fixing only one was not enough** — fixing only the gate left the session's `accelbyteId` blank and the fallback returned the connectionId anyway.

**The pre-existing KDoc warning that documented the contract but was never wired:** `RestPlayerSession.kt:51-62` reads "The AccelByte userId extracted from the SSE `accelbyteId` query parameter at registration time. The map-upload gate uses this as the canonical storage userId (the gate layer's `playerId` is the SSE/REST connectionId, which is a session-local identifier — the catalogue and AGS records are scoped by the AccelByte userId)." The intended wiring existed in design but not in code.

**Fix — both layers:**

```kotlin
// ServerExtend.kt — SSE /events handler MUST stamp accelbyteId on the session
val accelbyteId = call.request.queryParameters["accelbyteId"]?.takeIf { it.isNotBlank() } ?: ""
val registration = connectionManager.register(playerId, origin, accelbyteId)

// MapUploadGate.kt — resolve accelbyteId from the live session, fall back
// to the connectionId when the session has no accelbyteId (legacy curl
// probes, test rigs, skipLogin paths without an OAuth callback).
private suspend fun resolveAccelbyteUserIdForSave(connectionId: String): String
{
    val manager = MapUploadSuccessHandlers.currentConnectionManager() ?: return connectionId
    val session = runCatching { manager.findSession(connectionId) }.getOrNull() ?: return connectionId
    val accelbyteId = session.accelbyteId
    return accelbyteId?.takeIf { it.isNotBlank() } ?: connectionId
}

// savePack call site:
MapUploadGateStorage.savePack(
    context = context,
    userId = resolveAccelbyteUserIdForSave(context.connectionId),
    mapId = mapId,
    mapName = mapName,
    mapPackBytes = request.mapPackBytes
)
```

**Tests pinning the contract (2026-08-13, RED-before / GREEN-after on both files):**

| Test | What it pins |
|---|---|
| `MapUploadGateCatalogueUserIdTest.catalogWrittenUnderAccelbyteId_resolvesAccelbyteIdForSavePack` | Gate passes `accelbyteId` to `savePack`, not `playerId`. RED before fix. |
| `MapUploadGateCatalogueUserIdTest.catalogWrittenUnderConnectionId_fallsBackWhenNoAccelbyteId` | Boundary pin: legacy no-accelbyteId sessions still save under `playerId`. |
| `MapUploadGateCatalogueUserIdTest.catalogWrittenUnderAccelbyteId_dedupesByNameWithinTheSameUser` | The dedupe-by-name lookup runs under the same `userId` as the save. |
| `ServerExtendSseAccelbyteIdTest.sseRegisterAccelbyteIdIsStampedOnSession` | SSE `/events?accelbyteId=X` results in `session.accelbyteId == X`. RED before fix — the SSE handler called `register(playerId, origin)` without the third argument. |
| `ServerExtendSseAccelbyteIdTest.sseRegisterWithoutAccelbyteIdCarriesEmptyStringForFallback` | Boundary pin: legacy SSE clients without `?accelbyteId=` register with `accelbyteId = ""` so the gate's fallback works. |

The SSE-handler test uses `testApplication { application { serverModule() } client.get("/player"); ...; client.get("/events?playerId=X&accelbyteId=Y") }` then reads `m.findSession(playerId)?.accelbyteId` via the `testHooks_lastConnectionManager` test hook. This is the right shape for any future SSE-registration-regression test — the live `testApplication` block exercises the actual Ktor route, not a stub.

**Live probe (the operator's exact scenario):** `kvisionApp-e2e/probes/catalogue-refresh-2026-08-13.mjs` boots the dev stack, opens the Collection overlay, uploads a real `.map` zip (`kvisionApp-e2e/tests/fixtures/realistic-map.map` — 512×512 PNG + populated mapData), waits for `Map.Upload.Success`, and asserts the Maps tab auto-refreshed with a card carrying `data-testid="map-card-<real-uuid>"`. The probe also greps `/tmp/autogenesis-proxy/se.log` for `NoOpCataloguePersister: dropping write for <key>` — the persistent verification that the save landed in the right partition. Pre-fix: `dropping write for rest-client-<n>`. Post-fix: `dropping write for guest-user` (or whatever the AccelByte id is). This is the ONLY reliable way to confirm the partition match — the JVM tests use `fakeSaver` which doesn't touch the real `PlayerMapRepository`.

**Three-layer diagnosis protocol (verify ALL three before claiming fixed):**
1. JVM: `MapUploadGateCatalogueUserIdTest` — proves the gate's `savePack` call carries the right `userId`.
2. JVM: `ServerExtendSseAccelbyteIdTest` — proves the SSE registration stamps `accelbyteId` on the session.
3. Live: catalogue-refresh probe + `grep NoOpCataloguePersister /tmp/autogenesis-proxy/se.log` — proves the partition actually matches the client-side read.

**Anti-pattern (will burn an hour the way it burned me 2026-08-13):** fixing only layer (1) — the gate's userId resolution — without fixing layer (2) — the SSE handler's missing `accelbyteId` argument to `register()`. The gate's `resolveAccelbyteUserIdForSave` falls back to `connectionId` when `session.accelbyteId` is blank, so the JVM tests pass, but the live catalogue save still lands in the wrong partition. The `NoOpCataloguePersister` server log line is the diagnostic — if it shows `rest-client-<n>` instead of `guest-user`, the SSE handler is the bug, not the gate.

**Restart-required warning (operator-direction implication):** when the JVM was running with the pre-fix code, simply editing the source on disk did NOT take effect — `:server-extend:run` had built and started before the patch landed. The catalogue-refresh probe ran against the old code, the catalogue still keyed on `rest-client-<n>`, and the assertion failed. The fix: `fuser -k 7070 9080 8080; bash debugger/scripts/start_servers.sh` (or the `autogenesis-local-dev` skill's canonical kill pattern). The server log timestamp vs `ls -la build/libs/server-extend-*.jar` is the diagnostic. **Always check the running JVM's build time against the source mtime before claiming a fix took effect.**

**Companion reference:** `references/catalogue-refresh-2026-08-13.md` for the full session reproduction (operator's screenshot, the four-bug surface, the live probe's phase-by-phase walkthrough including the MessageBox leftover-overlay phase-B gotcha, the JVM suite transitions from RED to GREEN).

## The probe harness pattern (Playwright + Node.js)

**Shape:** A standalone Node.js script under `kvisionApp-e2e/probes/<flow-name>.mjs` that:
1. Navigates to the app URL.
2. Drives the UI through Phases (1-N) with assertion at each phase.
3. Captures screenshots at each phase (`screenshots/YYYY-MM-DD-<context>/<phase>-<step>.png`).
4. Captures all console output (info/warn/error) and writes to `all-console.txt`.
5. Reports: `assertions: N, passes: M, failures: K` with a list of failed check names.

**The probe is a contract test, not a smoke test.** Each assertion must check observable state (DOM presence, text content, button state, badge count, console error absence). Pseudo-assertions like `assertTrue(true, "did the thing")` are slack and hide real bugs.

**Selector pitfalls (Map Upload modal, verified 2026-08-12):**
- **Wrong selectors**: `upload-map-button` does NOT exist — the actual button is `[data-testid="maps-upload-button"]`. The "Maps" tab inside the collection overlay is a `<button class="collection-tab-button" title="Maps">` with NO `data-testid` — locate via `.collection-tab-button[title='Maps']` or click the title via `evaluate(() => ...)` over `document.querySelectorAll('.collection-tab-button')`. The Collection button on MainMenu is identified by TEXT (`b.textContent.trim() === 'Collection'`) — no data-testid on the button itself, only on the container.
- **Loading screen CTA**: every `?skipLogin=true` navigation lands on the loading screen first. Click `[data-testid="loading-screen-cta"]` to dismiss before waiting on `[data-testid="main-menu"]`. If you skip this step, `main-menu` never mounts and the probe times out at 30s.
- **Bridge-stabilize reload**: after the publish click, the dev bridge may still be racing the boot storm. A `page.reload()` (or `page.goto('?skipLogin=true')`) re-binds the bridge to a clean single-channel state. Wait 5s after reload before firing the publish again.
- **Text content drift**: a throbber that says "Uploading map…\nValidating and saving. This may take up to 30 seconds." is captured by `text="Uploading map…"` only if the assertion is `expect(text.startsWith("Uploading"))` — not `expect(text === "Uploading map…")`. Use prefix matching for multi-line throbber text.
- **File input**: `setInputFiles` on a hidden `<input type="file">` times out if the modal isn't open yet. Always open the modal, wait for `data-testid="map-upload-file-input"` to be visible, then set the file.
- **Transient selector timeout**: 30s default is enough for most cases; if a selector times out mid-phase, check if the modal closed (modal-dismiss on success) before retrying.
- **webpack-dev-server ERR_ABORTED on reload**: the dev server can interrupt navigations with hot-reload frames. Fall back to `waitUntil: 'domcontentloaded'` instead of `'load'` for re-navigation, and wrap the reload in `try { ... } catch { ... }` so a single ERR_ABORTED doesn't kill the probe.

**Building a realistic PNG fixture for the upload flow (2026-08-12):**
```python
# Use Pillow to draw a recognizable map (≥512x512 px so the LLM can see it):
W, H = 512, 512
img = Image.new("RGB", (W, H), (40, 60, 80))  # dark slate background
draw = ImageDraw.Draw(img)
# Three named territories, pin dots, connection lines:
draw.rectangle([20, 20, 240, 240], fill=(120, 80, 60), outline=(220, 200, 100), width=3)
# ... (pins + connections — see kvisionApp-e2e/probes/realistic-map-upload-e2e.mjs for the full recipe)

# Pack into a .map zip with the gate's expected shape:
import io, zipfile, json
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("map.json", json.dumps(map_data))  # pins + connections + worldName + ...
    z.writestr("map.png", img_bytes)
```

**The `mapData` must include `pins` (with `pinId` + `territory.name` + `xPos` + `yPos` + `adjacentTerritoryNames` fields), `connections` (with `fromPinId` + `toPinId`), `worldName`, `storyScenario`, and `author`. Smaller images (4×4 px / 72 bytes) get rejected by Nova Lite with "Image not provided for inspection" because the model literally cannot classify a 4-pixel blob.

**`map.json` shape is `MapPackData`, NOT bare `MapData` (verified 2026-08-13):** the wire format wraps the map data in `MapPackData(imageName: String, mapData: MapData)`. A probe that writes bare `{pins, connections, worldName, ...}` into `map.json` will fail with `Unpack failed: Map.json is not a valid MapPackData (Fields [imageName, mapData] are required for type with serial name 'structs.MapPackData', but they were missing at path: $)`. The correct shape:
```python
map_data = {
    "imageName": "map.png",   # entry name inside the zip
    "mapData": {
        "pins": [{"pinId": "p-A", "territory": {"name": "Alpha"}}],
        "connections": [{"fromPinId": "p-A", "toPinId": "p-B"}],
        "worldName": "...",
        "storyScenario": "",
        "author": "..."
    }
}
```
The zip entries themselves stay `map.json` and `map.png` (or whatever the image entry name is). See `sharedModel/src/commonMain/kotlin/structs/MapPack.kt:10` for the source-of-truth schema and `MapPackManager.pack` for the production packing logic.

**Bridge-state verification:** Mid-phase, after publish click, check `data-state="publishing"` on the publish button. Then check `text="Publishing…"` (with ellipsis char). Then check `disabled` on cancel/close buttons. Then check throbber visibility. THEN poll for outcome with a 60s timeout. The publish→outcome wait must use a polling loop with `{page.waitForFunction(...)}` — not a single `await page.waitForX()` call that fires once and times out.

## Empty-pack content-validation (operator directive, 2026-08-12)

**The operator's verbatim question:** "If a player tries to upload a map, and the map portion is either all default, or null IE: They did not supply a valid map data class does the flow stop there and error out? Or does it run forward to the agent wasting usage for no reason? Is there a check to make sure the contents of a map pack actually contains both an image and map data before running the agent?"

**Audit answer (the leak the operator caught):** the prior gate had THREE failure modes, only one of which was correctly handled.

| Scenario | Agent ran? | Why |
|---|---|---|
| Pack missing `map.json` | ❌ No | `MapPackManager.unpack` threw NPE on `mapPackData!!`; gate's `catch (e: Exception)` caught it. |
| Pack missing image entry | ❌ No | Same NPE path on `imageBytes!!`. |
| `map.json` parses but `MapData` is all-defaults (`pins: []`, `connections: []`, blank strings) | ✅ **YES — leaked** | Unpack succeeded, gate flow continued, BOTH safety pipes ran on empty content. Nova Lite rejected with "Image not provided" (4×4 fixture) or accepted a meaningless pass (realistic PNG with empty metadata). **Tokens burned for nothing.** |

**Fix — gate-level content validation, fail-fast AFTER unpack but BEFORE downsample:**

```kotlin
// MapUploadGate.kt — between the unpack (step 1) and the downsample (step 2/3)
if (payload.imageBytes.isEmpty())
{
    val reason = "Map pack is empty: image entry has zero bytes"
    MapUploadErrorHandlers.sendMapUploadError(playerId, reason)
    return MapUploadGateResponse(accepted = false, reason = reason)
}
if (payload.mapData.pins.isEmpty() && payload.mapData.connections.isEmpty())
{
    val reason = "Map pack is empty: no pins or connections in map data"
    MapUploadErrorHandlers.sendMapUploadError(playerId, reason)
    return MapUploadGateResponse(accepted = false, reason = reason)
}
```

The validation sits BETWEEN the unpack (so we have a valid `MapData` to inspect) and the downsample pre-flight (so the rejection is cheap — no `ImageIO.read` for empty bytes) and the safety pipeline (no LLM call). The cost-control win: an empty pack is rejected in microseconds, not 30+ seconds of Nova Lite round-trip with no useful signal.

**Why not reject all-defaults with blank strings but non-empty pins?** A blank `worldName` is fine — the writing agent fills it in. A blank `storyScenario` is fine. An empty image or zero pins/connections is NOT fine — there's literally nothing for the LLM to inspect. The check is the minimal "this pack is a real upload" test, not a "this is a high-quality upload" test.

**Tests pinning the contract (all in `MapUploadGatePackContentValidationTest`, 2026-08-12):**

1. `emptyImageBytesFailsFastBeforeSafetyPipeline` — zero-byte image bytes; asserts `accepted=false` AND `safetyRunnerCalled=false`. RED before the fix (gate was returning `accepted=true` for empty bytes because `downsampleImageBytes` was a no-op fast path that returned the empty array unchanged).
2. `emptyMapDataFailsFastBeforeSafetyPipeline` — `MapData(pins = emptyList(), connections = emptyList())` with a valid image; same assertions.
3. `mapPackUnpackExceptionMessageSurfacesVerbatim` — the typed exception (see next section); asserts the gate's `response.reason` is exactly `"Unpack failed: No map.json entry found in zip"` (the message the fake unpacker throws + the gate's `catch`-block prefix).

**Downstream test impact:** the existing `MapUploadGateTest` and `MapUploadGateDownsamplePreFlightTest` use an `emptyMapData()` helper that returned `MapData(pins = emptyList(), connections = emptyList())` for the happy-path tests of safety/save/downsample. After this fix, those tests' helper had to be updated to a non-empty `MapData` (one `PinData` + one `ConnectionData`) so they still exercise the safety pipeline. The downstream tests were testing the gate's downstream logic, not the content-validation; the new `MapUploadGatePackContentValidationTest` owns the content-validation contract.

**Common mistake to avoid:** don't add the content validation INSIDE the safety agent. The agent shouldn't know about the gate's content policy. The gate is the load-bearing control point — fail-fast happens BEFORE the agent is built, so the agent never sees a payload it can't usefully inspect. Putting the check in the agent would still build the pipeline, run pre-init, and consume state machine cycles before rejecting.

## Typed unpack exception pattern (MapPackUnpackException, 2026-08-12)

**Symptom (pre-fix):** when a player uploaded a malformed zip (missing `map.json`, missing image, or `map.json` with unparseable JSON), the gate's `MapUploadError` carried `"Unpack failed: null"` because `MapPackManager.unpack` used `!!` to NPE on the missing field. The `!!` exception message was the JVM's `NullPointerException` (no field name, no context), and the `catch` block prefixed it as `"Unpack failed: ${e.message}"` → `"Unpack failed: null"`. The operator got a useless error and no way to diagnose.

**Fix — typed `MapPackUnpackException` in sharedModel/commonMain:**

```kotlin
// sharedModel/src/commonMain/kotlin/structs/MapPack.kt
class MapPackUnpackException(message: String) : RuntimeException(message)
```

The exception is in commonMain so both the JVM and JS unpackers can throw it. It extends `RuntimeException` (not `Exception`) so it propagates through the gate's `catch (e: Exception)` block without a class-loader issue.

**Replace `!!` with named throws in both unpackers:**

```kotlin
// sharedModel/src/jvmMain/kotlin/structs/MapPackManager.kt (JVM)
val packData = mapPackData
    ?: throw MapPackUnpackException("No map.json entry found in zip")
val image = imageBytes
    ?: throw MapPackUnpackException("No image entry found in zip (expected one entry beside map.json)")

// Also wrap kotlinx.serialization failures:
mapPackData = try {
    RpcJson.decodeFromString(MapPackData.serializer(), jsonString)
} catch (e: Exception) {
    throw MapPackUnpackException(
        "Map.json is not a valid MapPackData (${e.message ?: e::class.simpleName})"
    )
}
```

The JS unpacker at `sharedModel/src/jsMain/kotlin/structs/MapPackManager.kt` uses the same shape — `zip.file("map.json") ?: throw MapPackUnpackException(...)`, `try { decodeFromString } catch { throw MapPackUnpackException(...) }`. The `e.message ?: e::class.simpleName` fallback handles the case where the SerializationException's message is null (rare but happens with deep JSON structural errors).

**Gate catch is unchanged** — `catch (e: Exception)` in `MapUploadGate.uploadMapGate` still catches, still surfaces `"Unpack failed: ${e.message}"`. The fix is purely in the exception type, not in the gate's catch contract. The third `MapUploadGatePackContentValidationTest` (above) verifies the message surfaces verbatim:

```kotlin
// Fake unpacker that simulates a malformed pack:
MapUploadGate.fakeUnpacker = { _ ->
    throw structs.MapPackUnpackException("No map.json entry found in zip")
}
// After gate runs: response.reason == "Unpack failed: No map.json entry found in zip"
```

**Why `RuntimeException` not a sealed class hierarchy:** the gate's catch is generic (`catch (e: Exception)`), and the per-exception-name pattern would require either multiple catch arms (verbose) or pattern matching (requires the gate to know the exception types, which is the wrong dependency direction — the gate shouldn't import all the exception types the lower layer might throw). `RuntimeException` with a descriptive `message` is the right contract: the gate catches everything, the exception type's `message` is the source of truth, and adding new error conditions means adding a new message string, not a new class.

**The `[REDACTED].` placeholder pattern in the trace JSON's `reasoningContent` field** is a separate but related observability concern — the operator's prior `★ Insight` block on the original design noted that `reasoningContent: [REDACTED].` is the right pattern for any reasoning tokens that contain proprietary data. MapPackUnpackException messages are short and never contain user content (just "No map.json entry found in zip" type strings), so they don't need redaction in the trace.

## Verifier-driven bug surfacing (2026-08-13)

**Pattern:** when shipping a class-level fix, build a small bash verifier script at `/tmp/hermes-verify-<feature>-<date>.sh` that runs every step a "green claim" requires:
- Compile-only checks (`:kvisionApp:compileTestKotlinJs` for JS test files)
- JVM test runs (`:server-extend:test --tests "..."`)  
- Live e2e probe assertions (parse `results.json` for `pass=N, fail=M` and shape checks)
- Source-level invariants (`grep -cE ...`, `grep -n ...`)

**Why this matters:** a verifier catches the gap between "test passes" and "the artifact you actually shipped is valid." In the 2026-08-13 operator-fixes iteration, the JVM tests passed (downsample suite green) and the live probe passed (MessageBox OK click collapses overlay). But the verifier's `:kvisionApp:compileTestKotlinJs` step surfaced a REAL compile error in the new `MessageBoxOkClosesDialogTest.kt` — the file had `container.appendChild(box.getElement())` where `getElement()` returns `Element?` but `appendChild` requires `Node`. Without the explicit compile step, the broken test would have shipped, masquerading as a regression pin that wouldn't run.

**Verifier recipe (kept as a skill-output reference):**
```bash
#!/usr/bin/env bash
set -uo pipefail
OVERALL=0
declare -A RESULTS
pass() { echo "[PASS] $1"; RESULTS["$1"]="PASS"; }
fail() { echo "[FAIL] $1 — $2"; RESULTS["$1"]="FAIL"; OVERALL=$((OVERALL+1)); }
hdr()  { echo "==================================================================="; echo "$1"; echo "==================================================================="; }

# Step 1: JVM suite (catches business-logic regressions)
hdr "Step 1 — JVM suite"
./gradlew :server-extend:test --tests "..." --no-daemon --console=plain > /tmp/jvm.log 2>&1
if [ "$?" = "0" ]; then pass "jvm_suite"; else fail "jvm_suite" "see /tmp/jvm.log"; fi

# Step 2: compile-only checks (catches broken test code)
hdr "Step 2 — JS test compile"
./gradlew :kvisionApp:compileTestKotlinJs --no-daemon --console=plain > /tmp/jscompile.log 2>&1
if [ "$?" = "0" ]; then pass "js_test_compiles"; else fail "js_test_compiles" "see /tmp/jscompile.log"; fi

# Step 3: live probe assertions (catches wiring regressions)
hdr "Step 3 — Live e2e probe"
if [ -f "$ART_DIR/results.json" ]; then
    # parse pass / fail / shape
    ...
fi

# Step 4: source-level invariants (catches regression-shaped returns)
hdr "Step 4 — Source invariants"
GR=$(grep -cE '^[[:space:]]+this.parent?.remove(this)' path/to/MessageBox.kt || true)
if [ "$GR" = "0" ]; then pass "no_detach"; else fail "no_detach" "..."; fi

# Summary
hdr "SUMMARY"
echo "Overall failures in this verifier: $OVERALL"
for k in "${!RESULTS[@]}"; do echo "  ${RESULTS[$k]}  $k"; done | sort
exit $OVERALL
```

**Naming convention:** `/tmp/hermes-verify-<feature>-<date>.sh` with `hermes-verify-*` prefix (NOT in the repo — session artifact). The `scripts/hermes-verify-targeted-suite.sh` in the `autogenesis-resume-flow-e2e` umbrella is the equivalent of a session-local helper, not a regression-shaped library.

**Two-mode split (loader-skill rule):** the verifier's output must label itself as "ad-hoc verification, not suite-green." A green verifier means the targeted checks passed; it does NOT mean the full test suite is green. Pre-existing failures (e.g. `MapUploadGateEndToEndTest`'s 3 tests, broken by `MapUploadSafetyBilling.recordSafetyUsage`'s `ExtendConfig.debugMode=true` short-circuit at `MapUploadSafetyBilling.kt:94-102` — unrelated to the iteration) are out of scope and must be flagged as such in the SUMMARY block.

## Files of interest

- `kvisionApp-e2e/probes/map-upload-e2e.mjs` — the canonical upload probe (skipLogin + small fixture, fast ~30s round-trip)
- `kvisionApp-e2e/probes/realistic-map-upload-e2e.mjs` — the realistic-PNG probe (full UX + 65s two-pipe round-trip)
- `kvisionApp-e2e/probes/artifacts-map-upload-e2e/*.png` — per-phase screenshots
- `kvisionApp-e2e/probes/artifacts-realistic-flow/*.png` — realistic-flow screenshots
- `kvisionApp-e2e/tests/fixtures/tiny-map.map` — 4×4 PNG fixture (rejected by LLM as "Image not provided")
- `kvisionApp-e2e/tests/fixtures/realistic-map.map` — 512×512 PNG fixture (accepted by LLM, both pipes vote PASS)
- `~/.tpipe/debug/trace/MapUploadGate/trace.json` — full LLM call trace (model ARN, request/response tokens, reasoning content)
- `~/.aws/inference.txt` — TPipe Bedrock SDK inference profile config (model ID → ARN map, auto-loaded at startup)
- `~/.autogenesis/logs/server-extend-*.log` — server-side logs (look for `MapUploadGate:` prefix for gate events)
- `server-extend/src/test/kotlin/network/MapUploadGateDownsamplePreFlightTest.kt` — pins the `MAX_SAFE_BINARY_BYTES` calibration + the downsample-pre-flight firing for a 1.58 MB image

## References

- `references/catalogue-refresh-2026-08-13.md` — session reproduction for the two-layer userId partition bug: the operator's exact screenshot, the four-bug surface (gate + SSE + MessageBox leftover + billing dev-mode bypass), the live probe's phase-by-phase walkthrough including the MessageBox leftover-overlay phase-B gotcha, the JVM suite transitions from RED to GREEN, and the restart-required warning
- `references/iterated-downsample-2026-08-13.md` — full session detail for the 256 K-token floor recalibration: the constant derivation, the iterated-halving helper shape (real + fake), the four new tests, the MessageBox fix shape, the ad-hoc verifier recipe, the high-entropy-PNG pitfall, and the MapPackData wire-format pitfall (must wrap `{imageName, mapData}`, not bare `{pins, connections}`)
- `references/bridge-storm-diagnosis.md` — the 4-iteration root-cause timeline with code shapes at each step
- `references/dev-mode-safety-bypass.md` — the bypass-flag pattern with `DEV_SAFETY_LIVE_TEST=1` opt-in, including the trace JSON anatomy for confirming a real Bedrock round-trip (now kept for historical reference only — bypass was removed in 1.1.0)
- `references/probe-harness-anatomy.md` — the 28-check probe structure, selector pitfalls, and the bridge-stabilize reload pattern (Phase 5b)
- `references/two-tree-workspace-pitfall.md` — autogenesis workspace vs `Open-Autogenesis` (bedrock ARNs / AB tenant URLs stripped) — cd to the nested tree first, confirm `gradlew` exists at the path you land on, before launching any boot script
- `references/restart-pattern.md` — the `kill -9 + sleep + ss -tlnp | grep :PORT` loop that's load-bearing for getting the dev stack back up after a server-extend build
- `references/safety-agent-original-design.md` — full reproduction of the two-pipe `buildMapSafetyAgent` with per-pipe `setOnFailure` callbacks, the JSON-parsing contract, the MiniBank playerId stash, and the per-pipe reason extraction — what "the original design" means and why each part exists

## Catalogue thumbnail rendering + CSS data-URL quirks (2026-08-13)

**Operator symptom:** "the image for the map is massive and blank." The catalogue's Maps tab shows a giant solid-color rectangle where the map thumbnail should be — no image rendered, just a gradient background.

**Where it lives:** `kvisionApp/src/jsMain/kotlin/ui/CollectionOverlay.kt` rebuilds the catalogue after `Map.Upload.Success`. The map card's `.co-thumb` div is supposed to show the uploaded PNG. The pre-fix code only put a `fas fa-map` icon there.

**Three implementation layers (all must be wired):**

1. **Renderer class** (`kvisionApp/src/jsMain/kotlin/ui/MapCardThumbnailRenderer.kt`) — fetches the pack via `server.extend.getPlayerMap`, base64-encodes the PNG bytes, and stamps the result as a `data:image/png;base64,...` URL on the `.co-thumb` div's `style.background-image`. Class-level seam: a `fetcher: suspend (String) -> ByteArray` parameter so tests can drive the renderer without the live RPC stack.

2. **Wiring in `CollectionOverlay.rebuildMapCards`** — for every entry the overlay creates a `MapCardThumbnailRenderer(mapInfo = info, thumbDiv = <.co-thumb node>, fetcher = ::fetchMapPackBytes)` and calls `renderer.render()`. Order matters: `mount the card → resolve the thumb div → instantiate the renderer → render()` — but call `renderer.render()` AFTER `applyMapFilter()` so KVision's reactive style update on filter changes doesn't overwrite the renderer's `setAttribute("style", ...)`.

3. **CSS cascade — two non-obvious bugs** that block the image even after the renderer's `setAttribute` is correct:

   **Bug A: `data:` URL with `image/png;base64,...` MIME separator `;` is parsed as a declaration terminator.** The browser's CSS parser splits the inline-style attribute at `;` even inside a quoted `url("...")` string. `data:image/png;base64,iVBORw0KG...` gets split into `data:image/png` (invalid, dropped) and `base64,iVBORw0KG...` (orphan). Fix: percent-encode the `;` → `%3B` so the MIME separator survives the parser: `data:image/png%3Bbase64,iVBORw0KG...`. Do NOT percent-encode `,` or `=` — those are URL-special inside the data scheme and don't need encoding.

   **Bug B: `background-image: url(...) center/cover no-repeat` is an invalid combined declaration.** `background-image` accepts only a single image token; combining position/size/repeat tokens makes the declaration invalid (`CSS.supports('background-image: url(...) center/cover no-repeat')` returns false). Split into separate longhand declarations:
   ```
   background-image: url(<data>) !important;
   background-position: center !important;
   background-size: cover !important;
   background-repeat: no-repeat !important;
   ```
   Then the stylesheet's `background:` shorthand wins because the inline shorthand is invalid; once split, the longhands with `!important` win.

   **Combined failure mode:** the renderer's `setAttribute("style", "background-image: url(...) center/cover no-repeat !important; ...")` writes a value the browser rejects silently. `getComputedStyle().backgroundImage` falls back to the stylesheet's `background: linear-gradient(...)` and you get the giant solid-color rectangle — the operator's exact symptom.

**Diagnostic recipe (3 checks):**
```js
// Check 1: the inline style is actually set
thumbDiv.getAttribute('style').includes('data:image/png%3Bbase64')

// Check 2: the inline declaration is valid CSS (separate longhands)
CSS.supports('background-image', thumbDiv.style.backgroundImage)
CSS.supports('background-size', thumbDiv.style.backgroundSize)

// Check 3: getComputedStyle reflects the data URL, not the stylesheet gradient
window.getComputedStyle(thumbDiv).backgroundImage.startsWith('url("data:image/png')
```

If check 1 passes but check 2 fails → the combined longhand shortform was the bug (split it).
If check 2 passes but check 3 fails → cascade priority lost; check `style.getPropertyPriority('background-image')` — it should be `"important"` if `!important` was set.
If check 3 passes but the image isn't visible visually → the inline element is `display: none` or the parent has `overflow: hidden` clipping it.

**Wire-format gotcha (recurring):** `MapPackManager.unpack` on JS side uses `JSZip.loadAsync(uint8Array)`. The bytes must be a real typed `Uint8Array` backed by a fresh `ArrayBuffer` — `Uint8Array(other.buffer, offset, length)` where `other` is a regular JS `Array` (e.g. a Kotlin `ByteArray`) leaves `.buffer` undefined and JSZip throws "Can't find end of central directory". Fix: allocate a new typed array and copy byte-by-byte:
```kotlin
val arr = Uint8Array(this.size)
for (i in 0 until this.size) arr[i] = (this[i].toInt() and 0xff)
return arr
```
The `and 0xff` mask also converts signed `Byte` values (-128..127) into the unsigned 0..255 range that typed-array slots expect.

**Render-time gotcha — `MapPackManager.unpack` is called TWICE if the fetcher pre-unpacks:** if the fetcher does `MapPackManager.unpack(resp.mapPackBytes).imageBytes` and the renderer then does `MapPackManager.unpack(packBytes)`, the renderer receives PNG bytes (not a zip), which JSZip rejects. The single-unpack invariant: `fetcher` returns RAW `resp.mapPackBytes`; the renderer's own `unpackSafe` does the single decode.

**Test pattern (TDD):**
```kotlin
@Test
fun rendererSetsDataUrlOnCoThumbDiv() = runTest {
    val fakeFetcher: suspend (String) -> ByteArray = { _ ->
        // Return PNG bytes (just the 8-byte magic header is enough).
        byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    }
    val thumbDiv = (document.createElement("div") as HTMLDivElement).apply {
        className = "co-thumb"
    }
    val renderer = MapCardThumbnailRenderer(info, thumbDiv, fakeFetcher)
    renderer.renderForTest().join()
    assertTrue(
        thumbDiv.style.backgroundImage.contains("data:image/png%3Bbase64"),
        "thumbDiv style.backgroundImage must carry the data URL after render. Got: ${thumbDiv.style.backgroundImage}"
    )
}
```

**Live probe contract:** `kvisionApp-e2e/probes/thumbnail-wiring-2026-08-13.mjs` boots the dev stack, uploads a real `.map` zip, waits for the catalogue card to appear, then asserts `getComputedStyle(thumb).backgroundImage.startsWith('url("data:image/png')`. If the cascade is broken, the assertion fails and the probe saves a screenshot for visual inspection.

**Apply ordering (load-bearing):** `applyMapFilter()` MUST run before the `renderers.forEach { it.render() }` loop. `applyMapFilter` writes `entry.panel.display` which KVision's reactive update observes; if `render()` fires first, KVision's subsequent style update on filter pass can overwrite the renderer's `setAttribute`. See `CollectionOverlay.kt:478-510`.

## Cross-references

- `autogenesis-marketing` — for the demo-reel / hero-copy angle; the probe screenshots feed the marketing asset pipeline
- `media/video-highlight-extraction` — for converting probe screenshots into 3-format (gif/mp4/webm) demo assets
- `tpipe-trace-parser` — for parsing `~/.tpipe/debug/trace/MapUploadGate/trace.json` into readable post-mortem output
- `persona:bigwang` / `persona:ents` — the operator's voice for status reports; apply the Bigwang/Ents pitfalls before shipping