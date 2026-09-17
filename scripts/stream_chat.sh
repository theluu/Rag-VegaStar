#!/usr/bin/env bash
# Xem stream chat ngay trong terminal.
#   scripts/stream_chat.sh "Cho tôi thông tin về tàu KOTA GAYA"            # tạo hội thoại mới
#   scripts/stream_chat.sh "Tàu này của ai?" <conversation_id>              # hỏi tiếp trong hội thoại cũ
# Biến môi trường: API_URL (mặc định http://localhost:8000)
set -euo pipefail
API_URL="${API_URL:-http://localhost:8000}"
MESSAGE="${1:?Cần nội dung câu hỏi}"
CONV_ID="${2:-}"

if [[ -z "$CONV_ID" ]]; then
  CONV_ID=$(curl -sf -X POST "$API_URL/conversations" -H 'Content-Type: application/json' -d '{}' \
    | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
  echo "conversation_id: $CONV_ID" >&2
fi

BODY=$(python3 -c 'import sys, json; print(json.dumps({"message": sys.argv[1]}))' "$MESSAGE")
# -N: tắt buffer để thấy từng sự kiện ngay khi server gửi
curl -N -sS -X POST "$API_URL/conversations/$CONV_ID/chat" \
  -H 'Content-Type: application/json' -H 'Accept: text/event-stream' \
  -d "$BODY"
