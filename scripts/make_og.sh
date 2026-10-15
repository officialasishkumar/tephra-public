#!/usr/bin/env bash
# Render tephra/web/og.svg (the hand-drawn link preview) to tephra/web/og.png, 1200x630, offline.
# Uses resvg or rsvg-convert when present, else ImageMagick (magick or convert; its own renderer
# needs a font it can find). The PNG is committed; run this after editing og.svg. Fails when the
# PNG is over 150 kB (the preview budget).
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
svg="$here/tephra/web/og.svg"
png="$here/tephra/web/og.png"
if command -v resvg >/dev/null 2>&1; then
  resvg --width 1200 --height 630 --background '#05080c' "$svg" "$png"
elif command -v rsvg-convert >/dev/null 2>&1; then
  rsvg-convert --width 1200 --height 630 --background-color '#05080c' "$svg" -o "$png"
elif command -v magick >/dev/null 2>&1; then
  magick -density 96 -background '#05080c' "$svg" -resize 1200x630! -strip -define png:compression-level=9 "$png"
elif command -v convert >/dev/null 2>&1; then
  convert -density 96 -background '#05080c' "$svg" -resize 1200x630! -strip -define png:compression-level=9 "$png"
else
  echo "make_og.sh: needs rsvg-convert or ImageMagick (magick/convert)" >&2
  exit 1
fi
size=$(wc -c < "$png" | tr -d ' ')
if [ "$size" -gt 153600 ]; then
  echo "make_og.sh: og.png is $size bytes, over the 150 kB budget" >&2
  exit 1
fi
echo "wrote $png ($size bytes)"
