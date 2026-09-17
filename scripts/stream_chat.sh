#!/usr/bin/env bash
# Xem stream chat ngay trong terminal.
#   scripts/stream_chat.sh "Cho tôi thông tin về tàu KOTA GAYA"            # tạo hội thoại mới
#   scripts/stream_chat.sh "Tàu này của ai?" <conversation_id>              # hỏi tiếp trong hội thoại cũ
# Biến môi trường:
#   API_URL (mặc định http://localhost:8000)
#   API_KEY, hoặc API_USERNAME + API_PASSWORD khi server bật đăng nhập (AUTH_USERS)
set -euo pipefail
API_URL="${API_URL:-http://localhost:8000}"
MESSAGE="${1:?Cần nội dung câu hỏi}"
CONV_ID="${2:-}"

AUTH=()
if [[ -n "${API_KEY:-}" ]]; then
  AUTH=(-H "X-API-Key: $API_KEY")
elif [[ -n "${API_USERNAME:-}" ]]; then
  LOGIN=$(python3 -c 'import sys, json; print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))' \
    "$API_USERNAME" "${API_PASSWORD:?Cần API_PASSWORD}")
  TOKEN=$(curl -sf -X POST "$API_URL/auth/login" -H 'Content-Type: application/json' -d "$LOGIN" \
    | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])') || { echo "Đăng nhập thất bại" >&2; exit 1; }
  AUTH=(-H "Authorization: Bearer $TOKEN")
fi

if [[ -z "$CONV_ID" ]]; then
  CONV_ID=$(curl -sf -X POST "$API_URL/conversations" -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} -d '{}' \
    | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
  echo "conversation_id: $CONV_ID" >&2
fi

BODY=$(python3 -c 'import sys, json; print(json.dumps({"message": sys.argv[1]}))' "$MESSAGE")
# -N: tắt buffer để thấy từng sự kiện ngay khi server gửi
curl -N -sS -X POST "$API_URL/conversations/$CONV_ID/chat" \
  -H 'Content-Type: application/json' -H 'Accept: text/event-stream' ${AUTH[@]+"${AUTH[@]}"} \
  -d "$BODY"
