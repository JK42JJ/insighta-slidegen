#!/usr/bin/env bash
# selfcheck.sh OUT.pptx [MIN]  — 검증 통과 여부를 종료코드로 반환(자가수정 루프용)
set -e
OUT="$1"; MIN="${2:-12}"
python3 "$(dirname "$0")/validate_deck.py" "$OUT" --min-slides "$MIN"
