#!/usr/bin/env bash
# optimize-hero.sh — PNG/JPG to WebP + verify recipe for ttt-site heroes
#
# Usage: optimize-hero.sh <slug>
# Example: optimize-hero.sh 2026-06-30-jvm-ai-agent-framework-native-runtime
#
# Assumes:
#   - working directory is the ttt-site repo root
#   - mmx image generate already produced public/assets/blog/<slug>-hero_001.jpg
#   - ffmpeg with libwebp is installed
#
# Outputs:
#   - public/assets/blog/<slug>-hero.webp (primary, ship this)
#   - public/assets/blog/<slug>-hero.png  (fallback for browsers without WebP)
#   - exits non-zero if source is missing or conversion fails
#   - prints final byte sizes and HTTP-equivalent path check

set -euo pipefail

SLUG="${1:-}"
if [[ -z "$SLUG" ]]; then
  echo "usage: optimize-hero.sh <slug>" >&2
  exit 1
fi

ASSETS_DIR="public/assets/blog"
SOURCE_JPG="${ASSETS_DIR}/${SLUG}-hero_001.jpg"
SOURCE_PNG="${ASSETS_DIR}/${SLUG}-hero.png"
WEBP_OUT="${ASSETS_DIR}/${SLUG}-hero.webp"
PNG_OUT="${ASSETS_DIR}/${SLUG}-hero.png"

# Find whichever source exists (jpg from mmx, png if hand-shipped)
SOURCE=""
if [[ -f "$SOURCE_JPG" ]]; then
  SOURCE="$SOURCE_JPG"
elif [[ -f "$SOURCE_PNG" ]]; then
  SOURCE="$SOURCE_PNG"
else
  echo "ERROR: no source file at $SOURCE_JPG or $SOURCE_PNG" >&2
  exit 1
fi

echo "source: $SOURCE ($(stat -c%s "$SOURCE") bytes)"

# Convert to WebP — ffmpeg recipe from humanizer pre-launch checklist + ttt-site-blog pitfall
ffmpeg -y -i "$SOURCE" -c:v libwebp -q:v 82 -lossless 0 "$WEBP_OUT" 2>&1 | tail -5

# Verify WebP actually wrote bytes (ffmpeg exits 0 on missing source sometimes)
if [[ ! -s "$WEBP_OUT" ]]; then
  echo "ERROR: $WEBP_OUT is missing or zero bytes" >&2
  exit 1
fi

echo "webp:   $WEBP_OUT ($(stat -c%s "$WEBP_OUT") bytes)"

# Copy source as .png fallback (rename jpg to png, browsers don't actually care about extension for image data, but filename convention matters)
if [[ "$SOURCE" != "$PNG_OUT" ]]; then
  cp "$SOURCE" "$PNG_OUT"
  echo "png fallback: $PNG_OUT ($(stat -c%s "$PNG_OUT") bytes)"
fi

# Print final state
echo ""
echo "Final state:"
ls -la "${ASSETS_DIR}/${SLUG}-hero."*

echo ""
echo "Verification recipe (run after npm run build):"
echo "  curl -sS -o /dev/null -w \"WebP HTTP %{http_code} size=%{size_download}\\n\" \\"
echo "    http://127.0.0.1:4321/assets/blog/${SLUG}-hero.webp"
echo "  curl -sS -o /dev/null -w \"PNG  HTTP %{http_code} size=%{size_download}\\n\" \\"
echo "    http://127.0.0.1:4321/assets/blog/${SLUG}-hero.png"