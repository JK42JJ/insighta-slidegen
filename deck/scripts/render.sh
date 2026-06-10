#!/usr/bin/env bash
# render.sh PPTX [OUTDIR]  — pptx를 PNG로 렌더해 시각 QA에 사용
set -e
PPTX="$1"; OUT="${2:-/tmp/insighta_render}"
mkdir -p "$OUT"; rm -f "$OUT"/*.png "$OUT"/*.pdf 2>/dev/null || true
soffice --headless --convert-to pdf --outdir "$OUT" "$PPTX" >/dev/null 2>&1
PDF="$OUT/$(basename "${PPTX%.pptx}").pdf"
pdftoppm -png -r 110 "$PDF" "$OUT/slide" >/dev/null 2>&1
ls -1 "$OUT"/slide*.png
