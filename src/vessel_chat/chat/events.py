"""Sự kiện stream gửi về client (SSE).

token        {text}                              — mảnh văn bản trả lời
tool_call    {id, name, args}                    — LLM yêu cầu gọi tool
tool_result  {id, name, ok, summary}             — tool chạy xong (tóm tắt ngắn)
data         {data_id, kind, bbox, summary, tool_call_id} — dữ liệu bản đồ sẵn sàng tại GET /map-data/{data_id}
memory       {window_turns, summary_used, retrieved}     — (debug) ngữ cảnh bộ nhớ đã dùng
guardrail    {stage, action, kind, message, …}   — guardrail chặn / cảnh báo / che nội dung
error        {code, message}                     — lỗi; stream vẫn kết thúc bằng done
done         {message_id, turn, usage}           — kết thúc lượt
"""

import json
from dataclasses import dataclass


@dataclass
class Event:
    type: str
    data: dict

    def to_sse(self) -> dict:
        return {"event": self.type, "data": json.dumps(self.data, ensure_ascii=False, default=str)}
