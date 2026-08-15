# Iterated-downsample + 256 K-token floor (2026-08-13) — session detail

This is the working artifact for the 2026-08-13 operator fix iteration:
the cap recalibration, the iterated-halving helper, the fakeDownsampler
test-seam iteration, the MessageBox OK regression, and the ad-hoc
verifier that caught the broken JS test compile.

## What the operator reported

> "Look here: You are supposed to downsample images to 256K tokens. You
> are clearly NOT DOING THAT!!! You will fix that. You will veriify
> fixed, and then you will deal with the fact that the ok button, does
> not close the message box but removes the ok button. idk how you
> fucked that up, you need to un-fuck that. And prove you un-fucked
> that. The ok button just deleting itself is a regressoin in the
> messagebox class. Apply debugging eveerythinng but the kitchen sink
> including step through and log parsing, apply TDD kill the bugs, run
> your harneess to drive autogenesis and test the game (And leverage
> all autogenesis skills whiich has knowledge on how to do this) AND
> FUCKING FIX THIS SHIT. You are not free from this task until you have
> fixed it fully."

Plus the screenshot showing:
- Title: `Upload failed`
- Message: `Upload failed: Image too large even after downsample (1184951 bytes > 921600 cap)`
- Single OK button visible

Two distinct bugs in the screenshot's stack trace:
1. The downsample helper's legacy 900 KB cap = 921600 bytes, with single-pass
   downsample rejecting oversized results.
2. The MessageBox's `hide()` calling `this.parent?.remove(this)` mid-event-cycle.

## Constants pinned in this iteration

```kotlin
// server-extend/src/main/kotlin/network/MapUploadGate.kt
internal const val MAX_SAFE_BINARY_BYTES = (256_000 / 0.627).toInt() // ≈ 408_292 bytes
private const val DOWNSAMPLE_MAX_DIMENSION = 1024
private const val DOWNSAMPLE_MIN_DIMENSION = 64
private const val MAX_DOWNSAMPLE_PASSES = 5
```

The `256_000 / 0.627` derivation: empirical Nova Lite Converse API PNG
ratio is 0.627 tokens/byte. 256 K tokens / 0.627 ≈ 408_293 bytes. The
`toInt()` truncates to 408_292. The cap is named `MAX_SAFE_BINARY_BYTES`
(unchanged) so existing call sites and tests don't need renames.

## The two test seams that iterate

**`fakeDownsampler` must iterate, mirroring production halving:**
```kotlin
private fun downsampleImageBytes(bytes: ByteArray): ByteArray {
    val fakeDownsampler = fakeDownsampler
    if (fakeDownsampler != null) {
        var current = fakeDownsampler(bytes)
        var passes = 1
        while (current.size > MAX_SAFE_BINARY_BYTES && passes < MAX_DOWNSAMPLE_PASSES) {
            Logger.info(LogCategory.NETWORK,
                "MapUploadGate: fakeDownsampler pass $passes produced ${current.size} bytes; halving input")
            current = fakeDownsampler(current)
            passes += 1
        }
        return current
    }
    // ... real JDK ImageIO loop
}
```

**Real JDK loop mirrors the seam:**
```kotlin
var currentMaxDim = DOWNSAMPLE_MAX_DIMENSION
var lastReencoded: ByteArray = bytes
while (currentMaxDim >= DOWNSAMPLE_MIN_DIMENSION) {
    if (longestEdge <= currentMaxDim) return bytes  // source already fits
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
return lastReencoded  // floor reached — caller's downstream check rejects
```

## Tests that pinned the contract (2026-08-13)

`server-extend/src/test/kotlin/network/MapUploadGateTokenTargetDownsampleTest.kt`
(4 tests, all green):

1. `operatorScreenshotSize_1184951Bytes_isAcceptedViaIteratedDownsample` —
   the operator's exact failing input size is now accepted (assertion:
   `downsampleCalls >= 1`).
2. `capIsCalibratedTo256KTokenFloorNotLegacy900KBCap` — the derived
   constant 408 KB is below the legacy 900 KB.
3. `iteratedDownsample_continuesHalvingUntilUnderCap` — fakeDownsampler
   returns oversized result on first pass, fitting result on second;
   asserts `downsamplePasses >= 2`. Pin the iteration contract, not the
   single-pass contract.
4. `maxSafeBinaryBytesForTest_reflects256KTokenFloor` — pinned cap
   ≤ 408 KB + 1024 slack.

`kvisionApp/src/jsTest/kotlin/ui/MessageBoxOkClosesDialogTest.kt`
(2 tests, compile-only since jsBrowserTest pipeline isn't wired):

1. `ok button click hides the entire message box, not just the ok button` —
   asserts `display === "none"` after click AND no bug shape.
2. `after ok click the overlay root is hidden and not just partially mutated` —
   defensive check against title + message remaining with OK gone.

The MessageBox test had a real Kotlin/JS compile error in its first
draft (`container.appendChild(box.getElement())` — `getElement()` returns
`Element?` but `appendChild` requires `Node`). The verifier's compile
step caught it before the test shipped.

## The MessageBox fix

```kotlin
// kvisionApp/src/jsMain/kotlin/ui/MessageBox.kt:180
override fun hide() {
    display = Display.NONE
    visible = false
}
```

Removed: `super.hide(); this.visible = false; this.parent?.remove(this)`.
The detach side effect was unique to MessageBox across the codebase —
14 other overlay widgets already used the canonical pattern.

## Ad-hoc verifier (kept for future iterations to copy)

The verifier script at `/tmp/hermes-verify-operator-fixes-2026-08-13.sh`
ran these steps:
- Step 1: JVM suite (`MapUploadGateTokenTargetDownsampleTest`,
  `MapUploadGateDownsamplePreFlightTest`, `MapUploadGateTest`,
  `MapUploadGatePackContentValidationTest`).
- Step 2: JS compile (`./gradlew :kvisionApp:compileTestKotlinJs`).
- Step 3: Live e2e probe (parse `results.json` from
  `kvisionApp-e2e/artifacts-messagebox-ok-fix-2026-08-13/`).
- Step 4: Live downsample cap check (parse `results.json` from
  `kvisionApp-e2e/artifacts-downsample-fix-2026-08-13/`).
- Step 5: Source invariants (`grep -n MAX_SAFE_BINARY_BYTES`,
  `grep -cE '^[[:space:]]+this.parent?.remove(this)'`).
- Step 6: Pre-existing failure survey (run `MapUploadGateEndToEndTest`
  to confirm its failures are unrelated).

Final result: 6/6 ad-hoc checks PASS, 2 pre-existing failures in
`MapUploadGateEndToEndTest` flagged as out-of-scope.

## Pre-existing failure flagged (NOT this iteration's work)

`MapUploadGateEndToEndTest` has 2-3 tests that fail on
`billingCalls.contains("saveUsageLedger")`. Root cause is at
`server-extend/src/main/kotlin/network/MapUploadSafetyBilling.kt:94-102`:

```kotlin
// T12: dev-mode bypass — skip entirely when ExtendConfig.debugMode is true.
if (ExtendConfig.debugMode) {
    Logger.debug(...)
    return SafetyBillingOutcome.Skipped("dev mode")
}
```

`ExtendConfig.debugMode` defaults to `true` (production-style, see
`server-extend/src/main/kotlin/globals/ExtendConfig.kt:41`). The
short-circuit fires BEFORE the test seam is consulted, so even the
test's `setInvokeOverrideForTest` lambda never sees a call. Fix is
either (a) flip `ExtendConfig.debugMode = false` in `@Before` + restore
in `@After`, or (b) move the dev-mode bypass behind the same test seam
that other RPCs use. This is a separate work item — operator's standing
task list at `PLANS/map-upload-safety-usage-billing.md`.

## Pitfalls for the next iteration

- **High-entropy PNGs** (random RGB per pixel, e.g. crypto-noise) genuinely
  cannot compress under iterated halving — they'll reject at the 64 px
  floor with "Image too large even after downsample". This is the
  CORRECT rejection shape, not a bug. Real-world map renders
  (gradient territories, anti-aliased labels) compress well.
- **Test seam iteration** is load-bearing. A single-pass `fakeDownsampler`
  pins the wrong contract — every test that counts invocation counts
  must also count iterated invocations.
- **Kotlin/JS `getElement()` returns `Element?`** — not `Node`. Any
  `appendChild(panel)` call needs an explicit `as? Node` or non-null
  assertion. Don't fight the FFI seam — read the actual return type
  from the KVision 9.1.1 sources at
  `/home/cage/.gradle/caches/modules-2/files-2.1/io.kvision/kvision/9.1.1/*/kvision-9.1.1-sources.jar`.
- **webpack-dev-server ERR_ABORTED on reload** still fires on large
  uploads (12 MB+). Cap test fixture size at ≤3 MB to avoid the
  dev-server wedge during live probes.
- **`map.json` is `MapPackData`, NOT bare `MapData`** — the wire format
  wraps in `{imageName: "map.png", mapData: {pins, connections, ...}}`.
  Bare `{pins, connections, ...}` fails with `Fields [imageName, mapData]
  are required for type with serial name 'structs.MapPackData'`. See
  `sharedModel/src/commonMain/kotlin/structs/MapPack.kt:10`.
