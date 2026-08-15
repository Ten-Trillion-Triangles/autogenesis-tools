# MAX_SAFE_BINARY_BYTES — Empirical Calibration

The constant `MAX_SAFE_BINARY_BYTES` in `server-extend/src/main/kotlin/network/MapUploadGate.kt`
controls the gate's image-size pre-flight: any image larger than this threshold gets
downsampled to 1024×1024 max-dimension via JDK `BufferedImage` + `ImageIO` before
the safety pipeline runs.

## The empirical evidence

The original value was **3 MB** (`3 * 1024 * 1024`). It was empirically wrong.

A live Bedrock trace from 2026-08-12 against a 1.58 MB PNG overflowed Nova Lite's
990 K-token context window with the error:

```
Error: Context window size is too small to fit the binary data.
Please increase the context window size.
Context window size: 990000
Binary size: 1579421
```

The 1.58 MB image, at Nova Lite's empirical PNG token/byte ratio (~0.627 tokens/byte),
consumed ~990 K tokens — the entire window — leaving zero slack for the system
prompt, footer, JSON-schema examples, reasoning tokens, and the JSON verdict.

## The math

Nova Lite context window: 990,000 tokens (per `BedrockConfig.novaBudgetSettings.contextWindowSize`).

Empirical token/byte ratio for PNG input on Nova Lite Converse API:

```
990_000 tokens / 1_579_421 bytes ≈ 0.627 tokens/byte
```

At 0.627 tokens/byte:

| Image size | Token cost | % of 990 K window | Status |
|---|---|---|---|
| 100 KB | 63 K tokens | 6% | Safe (no downsample needed) |
| 500 KB | 313 K tokens | 32% | Safe |
| 900 KB | 564 K tokens | **57%** | **SAFE — leaves 426 K tokens / 43% for prompt/footer/reasoning/output** |
| 1.58 MB | 990 K tokens | 100% | **OVERFLOW** — no slack, model crashes |
| 3 MB | 1.88 M tokens | 190% | **WOULD OVERFLOW** — but pre-flight at 3 MB cap let it through unwritten |

The chosen cap is **900 KB** (`900 * 1024`): at 0.627 tokens/byte, the image
occupies ~564 K tokens ≈ 57% of the 990 K window, leaving ~426 K tokens / 43%
for everything else. That's the headroom the safety classifier needs to inspect
the image without overflowing.

## The constant

```kotlin
// server-extend/src/main/kotlin/network/MapUploadGate.kt:62-79
internal const val MAX_SAFE_BINARY_BYTES = 900 * 1024
```

`internal` (not `private`) so the test seam `maxSafeBinaryBytesForTest()` can
read it. The companion test seam:

```kotlin
internal fun maxSafeBinaryBytesForTest(): Int = MAX_SAFE_BINARY_BYTES
```

## The downsample helper

When `payload.imageBytes.size > MAX_SAFE_BINARY_BYTES`, the gate calls
`downsampleImageBytes(bytes)`:

```kotlin
private fun downsampleImageBytes(bytes: ByteArray): ByteArray
{
    val fakeDownsampler = fakeDownsampler
    if (fakeDownsampler != null) {
        return fakeDownsampler(bytes)
    }
    try {
        val src = ImageIO.read(ByteArrayInputStream(bytes))
            ?: throw RuntimeException("ImageIO.read returned null — bytes are not a decodable image")
        val srcW = src.width
        val srcH = src.height
        val longestEdge = maxOf(srcW, srcH)
        if (longestEdge <= DOWNSAMPLE_MAX_DIMENSION) {
            return bytes  // already small enough
        }
        val scale = DOWNSAMPLE_MAX_DIMENSION.toDouble() / longestEdge
        val dstW = (srcW * scale).toInt().coerceAtLeast(1)
        val dstH = (srcH * scale).toInt().coerceAtLeast(1)
        val dst = BufferedImage(dstW, dstH, BufferedImage.TYPE_INT_ARGB)
        val g = dst.createGraphics()
        try {
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC)
            g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g.drawImage(src, 0, 0, dstW, dstH, null)
        } finally {
            g.dispose()
        }
        val out = ByteArrayOutputStream()
        ImageIO.write(dst, "png", out)
        return out.toByteArray()
    } catch (e: Exception) {
        Logger.error(LogCategory.NETWORK, "MapUploadGate: downsample failed: ${e.message}; passing through original bytes")
        return bytes
    }
}
```

DOWNSAMPLE_MAX_DIMENSION = 1024 (constant). Output is PNG to match the MIME
type the safety pipe expects. The `try/catch` swallows downsample failures and
returns the original bytes — the gate then fails the safety check at the
model level rather than crashing the upload.

## The pre-flight code path

```kotlin
// server-extend/src/main/kotlin/network/MapUploadGate.kt
val imageBytes = if (payload.imageBytes.size > MAX_SAFE_BINARY_BYTES)
{
    Logger.info(LogCategory.NETWORK, "MapUploadGate: image size ${payload.imageBytes.size} bytes exceeds cap ${MAX_SAFE_BINARY_BYTES} bytes for playerId=$playerId; downsampling")
    val downsampled = downsampleImageBytes(payload.imageBytes)
    if (downsampled.size > MAX_SAFE_BINARY_BYTES)
    {
        val reason = "Image too large even after downsample (${downsampled.size} bytes > ${MAX_SAFE_BINARY_BYTES} cap)"
        Logger.error(LogCategory.NETWORK, "MapUploadGate: $reason for playerId=$playerId; rejecting")
        MapUploadErrorHandlers.sendMapUploadError(playerId, reason)
        return MapUploadGateResponse(accepted = false, reason = reason)
    }
    downsampled
}
else
{
    payload.imageBytes
}
```

The two-stage check (downsample once → if still over cap → reject) prevents an
infinite loop on pathological inputs (e.g. a 50 MB PNG that 1024×1024 still
exceeds 900 KB after compression due to noise). The named rejection reason
surfaces in the SSE notification so the UI can show the actual error.

## Test coverage

`server-extend/src/test/kotlin/network/MapUploadGateDownsamplePreFlightTest.kt`
pins both invariants:

1. `maxSafeBinaryBytesCapIsCalibratedForNovaLiteContextWindow` — checks that
   the threshold is below the empirical 1.58 MB overflow size AND that the
   image at the threshold stays under 70% of the 990 K window.
2. `downsamplePreFlightFiresForEmpiricalOverflowImageSize` — wires a 1.58 MB
   image through `uploadMapGate` with `fakeDownsampler` injected; asserts
   `downsampleCalled == true` after the call.

Both tests were GREEN after the 3 MB → 900 KB constant change. With the
old 3 MB constant, both would have been RED (the 1.58 MB image passes the
threshold check, downsample never fires, the model crashes on the raw 1.58 MB).

## Adjacent pitfalls

- **`ConfigSource.property()` throws on missing keys**: `bedrock.local.properties
  missing key 'bedrock.llamaScout17B'` is the misleading error log you see
  when initializing the Bedrock config. The throw happens inside an `init {}`
  block, is caught and logged, and the system continues with the missing
  binding. The safety pipeline uses `novaModelName`, NOT `llamaScout17B`,
  so this missing key is harmless noise. Use `propertyOrEmpty()` for non-critical
  bindings; reserve `property()` for required keys where failure should be loud.

- **The LiveTest also uses the old 3 MB cap**: `MapUploadSafetyAgentLiveTest.kt:114`
  has its own `maxSafeBytes = 3 * 1024 * 1024` constant for the downsample
  pre-flight before the live Bedrock call. If you re-run that test against an
  image in [1.5, 3.0] MB, the live test's pre-flight will pass the raw
  bytes through to the model and crash with the same "Context window size is
  too small" error. Update the LiveTest's constant to match `MAX_SAFE_BINARY_BYTES`
  for consistency.

- **The downsample output is ALWAYS PNG**: the helper uses
  `ImageIO.write(dst, "png", out)`. If the input was JPEG/WebP/etc., the
  bytes change format but the MIME type annotation in the safety pipe stays
  as `image/png`. The model handles this fine (PNG is a superset of the
  byte structure), but it's worth noting if you ever audit the trace.

- **Pillow fixtures for testing**: when generating a realistic PNG fixture
  for the probe (see `references/probe-harness-anatomy.md` for the recipe),
  a 512×512 PNG with simple geometry is ~3-4 KB packed, well under the
  900 KB cap. To exercise the downsample path, generate a fixture that's
  >900 KB — either a larger canvas (e.g. 2048×2048 with noise = ~2 MB) or
  one with a high-detail texture that doesn't compress well.