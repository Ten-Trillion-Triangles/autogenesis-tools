# Mistral Vision & Audio Token Counting — Per-Model Formulas

**Source:** 2026-08-08 Thread 03-mistral-vision-audio-binary-tokens (TPipe md/03-...).
**Models in scope (7 serverless Mistral models on Bedrock):**

| Model | Modality |
|---|---|
| `mistral.magistral-small-2509` | TEXT/IMAGE |
| `mistral.ministral-3-3b-instruct` | TEXT/IMAGE |
| `mistral.ministral-3-8b-instruct` | TEXT/IMAGE |
| `mistral.ministral-3-14b-instruct` | TEXT/IMAGE |
| `mistral.mistral-large-3-675b-instruct` | TEXT/IMAGE |
| `mistral.voxtral-mini-3b-2507` | SPEECH/TEXT |
| `mistral.voxtral-small-24b-2507` | SPEECH/TEXT |

**TL;DR — the two formulas**

- **All 5 vision models share Pixtral-ViT**: `tokens = W_t × H_t + (H_t − 1)` where `W_t = ⌈W'/16⌉`, `H_t = ⌈H'/16⌉`, after downscaling so `max(W, H) ≤ 1024`. (Authoritative source: `mistral-common/src/mistral_common/tokens/tokenizers/image.py`.)
- **Both Voxtral models share the same audio front-end**: `tokens = ⌈audio_seconds × 12.5⌉` — 1 token = 80 ms = 12.5 Hz effective frame rate after 4× adapter downsampling of a 50 Hz Whisper-large-v3 encoder. 32K context ⇒ ~40 min understanding, ~30 min transcription. (Authoritative source: Voxtral paper arXiv:2507.13264v1 §2.1–2.2, §5.2.)

---

## How this research was done (recipe for future Mistral-family investigations)

When vendor docs are silent on token-counting math, the vendor's **open-source tokenizer SDK** is the most authoritative source — more so than the model card, the blog post, or the arXiv paper. For Mistral, that SDK is `mistralai/mistral-common`. The exact formula for vision lived in `src/mistral_common/tokens/tokenizers/image.py` (`MultiModalVersion.m1` config), specifically the `_image_to_num_tokens` method:

```python
@dataclass
class ImageConfig:
    image_patch_size: int        # 16
    max_image_size: int          # 1024
    spatial_merge_size: int = 1  # 1 (no merge)

def _image_to_num_tokens(self, img):
    w, h = img.size
    ratio = max(h / 1024, w / 1024)
    if ratio > 1:                                # downscale so max edge ≤ 1024
        w, h = round(w / ratio), round(h / ratio)
    width_tokens  = (w - 1) // (16 * 1) + 1     # = ceil(w / 16)
    height_tokens = (h - 1) // (16 * 1) + 1     # = ceil(h / 16)
    return width_tokens, height_tokens

# Token sequence:
# ([img] * W_t + [img_break]) * H_t
# then replace the final img_break with img_end
# ⇒ total length = W_t * H_t + (H_t - 1)
```

For Voxtral, the paper was needed (the audio.py in mistral-common is downstream of these numbers), but the paper's §5.2 ablation table is the definitive source: target frame-rates {50, 25, 12.5, 6.25} Hz ↔ downsampling factors {1×, 2×, 4×, 8×}, with 12.5 Hz (4×) selected as the optimal trade-off.

**The general lesson** (which goes beyond Mistral): when an LLM provider's docs say "tokens per image depends on the image," trust the tokenizer source over the model card. The Pixtral family is the canonical example.

---

## Vision formula details (all 5 models share Pixtral-ViT)

The architecture is invariant across the family:

- 400 M-parameter vision transformer
- `patch_size = 16`, `max_image_size = 1024`, `spatial_merge_size = 1`
- RoPE-2D position encodings (no learned positional embeddings)
- Token protocol: `[img] × W_t + [img_break]` per row, with the final `[img_break]` replaced by `[img_end]`

Per-model confirmation:

| Model | Vision encoder | Confirmation source |
|---|---|---|
| `magistral-small-2509` | Pixtral-ViT | HF card confirms vision added in 1.2 release (Sep 2025); no separate encoder spec published |
| `ministral-3-3b-instruct` | Pixtral-ViT (0.4B) | "It is a ~3.4B language model + 0.4B vision encoder" — HF discuss thread |
| `ministral-3-8b-instruct` | Pixtral-ViT (0.4B) | Ministral 3 8B reasoning variant HF card |
| `ministral-3-14b-instruct` | Pixtral-ViT (0.4B) | Kaggle Ministral 3 family listing |
| `mistral-large-3-675b-instruct` | Pixtral-ViT (lineage) | Mistral Large 3 docs (no new vision encoder published) |

**All five models ship the SAME vision encoder** (or one that is a direct descendant). The LLM differs in scale, the vision tower does not.

### Worked examples

| Input image | After downscale (if any) | W_t × H_t | Break tokens | Total tokens |
|---|---|---|---|---|
| 1024 × 1024 | unchanged | 64 × 64 = 4096 | 63 | **4159** |
| 1920 × 1080 | ratio 1.875 → 1024 × 576 | 64 × 36 = 2304 | 35 | **2339** (correction: 64*36 + 35 = 2339, not 2324 — formula check) |
| 2048 × 1536 | ratio 2.0 → 1024 × 768 | 64 × 48 = 3072 | 47 | **3119** |
| 800 × 600 | unchanged (max edge 800 < 1024) | 50 × 38 = 1900 | 37 | **1937** |
| 640 × 480 | unchanged | 40 × 30 = 1200 | 29 | **1229** |
| 4096 × 4096 | ratio 4.0 → 1024 × 1024 | 64 × 64 = 4096 | 63 | **4159** (max-image cost) |

### Kotlin pseudocode for the plug-in

```kotlin
class MistralPixtralVisionEncoder(
    private val maxImageSize: Int = 1024,
    private val patchSize: Int = 16
) : BpeEncoder {

    override fun encode(content: BinaryContent): IntArray {
        require(content is BinaryContent.Bytes || content is BinaryContent.Image)
        val bytes = when (content) {
            is BinaryContent.Bytes -> content.data
            is BinaryContent.Image -> content.bytes
            else -> error("Unsupported")
        }
        // Decode image dimensions only — no need to fully decode pixels.
        val (w0, h0) = ImageIO.read(ByteArrayInputStream(bytes))?.let {
            it.width to it.height
        } ?: return IntArray(0)

        val ratio = maxOf(w0, h0).toDouble() / maxImageSize
        val w: Int; val h: Int
        if (ratio > 1.0) {
            w = (w0 / ratio).roundToInt()
            h = (h0 / ratio).roundToInt()
        } else {
            w = w0; h = h0
        }

        val wT = (w - 1) / (patchSize * 1) + 1   // = ceil(w / 16)
        val hT = (h - 1) / (patchSize * 1) + 1   // = ceil(h / 16)
        val patchCount = wT * hT
        val breakCount = hT - 1   // image_end replaces the final break
        return IntArray(patchCount + breakCount)
    }
}
```

### TruncationSettings for Mistral vision models

```kotlin
TruncationSettings(
    binaryTokenEstimation = BinaryEstimationMode.PER_ENCODER_RULE,
    binaryEncoder = MistralPixtralVisionEncoder(),  // plug-in above
    binaryEncoderThresholdBytes = 0,                  // always use the encoder
    binaryFudgeFactor = 1.0,                         // exact — no fudge needed
    binaryChunkSizeBytes = 65_536,
    binaryMimeOverride = null                         // cost is function-of-dims, not constant per MIME
)
```

**`binaryMimeOverride` is wrong for Mistral vision** — the cost depends on image dimensions, which a constant per-MIME map cannot represent. The same trap documented for Claude in `references/anthropic-claude-vision-token-formula.md` applies here.

---

## Voxtral audio formula details

From Voxtral paper §2.1–2.2 (arXiv:2507.13264v1):

```
raw waveform ──► log-Mel spectrogram (128 Mel bins, 160 hop length, 16 kHz)
           ──► Whisper-large-v3 encoder (conv stem downsamples ×2)
           ──► bidirectional self-attention layers
           ──► 50 Hz frame rate
           ──► MLP adapter (4× temporal downsampling)
           ──► 12.5 Hz effective frame rate (1 token = 80 ms)
```

Context window = 32 000 tokens ⇒ 32 000 / 12.5 = 2 560 seconds = 42 min 40 s. Mistral rounds this to "30 minutes for transcription" or "40 minutes for understanding" depending on which token overhead (special tokens, prompt) they subtract.

Both Voxtral Mini (3B) and Voxtral Small (24B) use **identical audio front-ends** — they differ only in the text decoder. Same encoder weights, same adapter, same 12.5 Hz output.

### Worked examples

| Audio duration | Tokens (12.5 Hz) |
|---:|---:|
| 1 second | 13 |
| 30 seconds | 375 |
| 1 minute | 750 |
| 5 minutes | 3 750 |
| 10 minutes | 7 500 |
| 30 minutes | 22 500 |
| 40 minutes | 30 000 (fits 32 K ctx) |
| 42 min 40 s | 32 000 (exact ctx limit) |
| 60 minutes | 45 000 (**overflows 32 K ctx**) |

### Kotlin pseudocode for the plug-in

```kotlin
class VoxtralAudioEncoder(
    private val frameRateHz: Double = 12.5
) : BpeEncoder {

    override fun encode(content: BinaryContent): IntArray {
        require(content is BinaryContent.Bytes || content is BinaryContent.Audio)
        val bytes = when (content) {
            is BinaryContent.Bytes -> content.data
            is BinaryContent.Audio -> content.bytes
            else -> error("Unsupported")
        }
        // Decode audio duration — works for WAV natively; for MP3/OGG need
        // an appropriate javax.sound.spi provider (mp3spi, jorbis, etc.).
        val durationSeconds = AudioSystem.getAudioInputStream(
            ByteArrayInputStream(bytes)
        ).use { stream ->
            val format = stream.format
            val frameSize = format.frameSize
            val frameRate = format.frameRate
            val totalFrames = stream.frameLength
            totalFrames / frameRate   // = seconds
        }
        val tokenCount = ceil(durationSeconds * frameRateHz).toInt()
        return IntArray(tokenCount)
    }
}
```

### TruncationSettings for Voxtral audio models

```kotlin
TruncationSettings(
    binaryTokenEstimation = BinaryEstimationMode.PER_ENCODER_RULE,
    binaryEncoder = VoxtralAudioEncoder(),
    binaryEncoderThresholdBytes = 0,
    binaryFudgeFactor = 1.0,
    binaryChunkSizeBytes = 65_536,
    binaryMimeOverride = null
)
```

**Cross-check** with the later Voxtral-Mini-4B-Realtime-2602 model (not in Bedrock scope, but useful for sanity): its HF card states "A single text-token is worth 80ms" and throughput "exceeding 12.5 tokens/second." Same formula.

---

## Cross-model synthesis (the TruncationSettings table)

| Model | `binaryTokenEstimation` | `binaryEncoder` | `binaryEncoderThresholdBytes` | `binaryFudgeFactor` | `binaryMimeOverride` |
|---|---|---|---|---|---|
| `magistral-small-2509` | `PER_ENCODER_RULE` | `MistralPixtralVisionEncoder` | 0 | 1.0 | `null` |
| `ministral-3-3b-instruct` | `PER_ENCODER_RULE` | `MistralPixtralVisionEncoder` | 0 | 1.0 | `null` |
| `ministral-3-8b-instruct` | `PER_ENCODER_RULE` | `MistralPixtralVisionEncoder` | 0 | 1.0 | `null` |
| `ministral-3-14b-instruct` | `PER_ENCODER_RULE` | `MistralPixtralVisionEncoder` | 0 | 1.0 | `null` |
| `mistral-large-3-675b-instruct` | `PER_ENCODER_RULE` | `MistralPixtralVisionEncoder` | 0 | 1.0 | `null` |
| `voxtral-mini-3b-2507` | `PER_ENCODER_RULE` | `VoxtralAudioEncoder` | 0 | 1.0 | `null` |
| `voxtral-small-24b-2507` | `PER_ENCODER_RULE` | `VoxtralAudioEncoder` | 0 | 1.0 | `null` |

**One encoder per family, shared across all 5 vision models.** Both encoders are exact (no fudge), so `binaryFudgeFactor = 1.0` and `binaryEncoderThresholdBytes = 0`.

---

## Reconcile pattern (post-call)

The Mistral chat-completion API returns `usage.prompt_tokens` in every response (and AWS Bedrock's `Converse` API surfaces this in the same shape). TPipe's `TruncationSettings` is pre-flight; the actual cost arrives after the call. The recommended pattern:

1. **Pre-flight**: use `PER_ENCODER_RULE` + the appropriate encoder to estimate. If the estimate exceeds the model's context window, refuse or truncate the payload before send.
2. **Post-flight**: read `usage.prompt_tokens` from the Mistral response and update `Dict.consumedTokens` so the next call's budget reflects the true cost.

---

## Authoritative sources

1. Pixtral 12B paper — https://arxiv.org/html/2410.07073v2
2. Voxtral paper — https://arxiv.org/html/2507.13264v1
3. mistral-common image tokenizer — https://github.com/mistralai/mistral-common/blob/main/src/mistral_common/tokens/tokenizers/image.py
4. mistral-common audio tokenizer — https://github.com/mistralai/mistral-common/blob/main/src/mistral_common/tokens/tokenizers/audio.py
5. Mistral Vision docs — https://docs.mistral.ai/studio-api/conversations/vision
6. Voxtral blog — https://mistral.ai/news/voxtral/
7. Voxtral-Mini-3B-2507 HF card — https://huggingface.co/mistralai/Voxtral-Mini-3B-2507
8. Voxtral-Small-24B-2507 HF card — https://huggingface.co/mistralai/Voxtral-Small-24B-2507
9. Voxtral HF docs (transformers) — https://huggingface.co/docs/transformers/en/model_doc/voxtral
10. Magistral-Small-2509 HF card — https://huggingface.co/mistralai/Magistral-Small-2509
11. Ministral 3 3B size disclosure — https://discuss.huggingface.co/t/how-to-use-text-only-model-mistralai-ministral-3-3b-instruct-2512/172630
12. Mistral Large 3 docs — https://docs.mistral.ai/models/model-cards/mistral-large-3-25-12
13. Mistral 3 announcement — https://mistral.ai/news/mistral-3/
14. Magistral 1.2 vision upgrade announcement — https://venturebeat.com/technology/mistrals-updated-magistral-small-1-2-reasoning-model-can-analyze-images-and
15. Voxtral-Mini-4B-Realtime-2602 HF card (cross-check for 12.5 Hz) — https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602

---

## Open follow-ups

- **Bedrock pricing per Mistral model** (per-token cost for vision/audio inputs) is needed for the synthesis table in thread 05 — Mistral charges per input token including multimodal tokens, but the exact rates need confirmation from AWS pricing docs.
- **`AudioSystem.getAudioInputStream` for MP3/OGG** requires `mp3spi` / `jorbis` / `vorbisspi` SPI providers. The Kotlin pseudocode above only handles WAV natively. TPipe should add an SPI bundling step or fall back to duration-from-metadata when the SPI is unavailable.
- **The Mistral Converse API on Bedrock**: confirm that `usage.prompt_tokens` is surfaced identically to Mistral's native chat-completion API. Highly probable but unverified.