"""Metrics Prometheus và log có cấu trúc."""

import json
import logging
import time

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter("vc_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("vc_http_request_seconds", "HTTP request latency (headers sent)", ["route"])

CHAT_TURNS = Counter("vc_chat_turns_total", "Chat turns", ["outcome"])
CHAT_TTFT = Histogram("vc_chat_first_token_seconds", "Time to first token",
                      buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34))
CHAT_DURATION = Histogram("vc_chat_turn_seconds", "Full turn duration",
                          buckets=(1, 2, 3, 5, 8, 13, 21, 34, 55, 89))
LLM_TOKENS = Counter("vc_llm_tokens_total", "LLM tokens", ["kind"])
LLM_COST = Counter("vc_llm_cost_usd_total", "Estimated LLM cost (USD)")

TOOL_CALLS = Counter("vc_tool_calls_total", "Tool calls", ["tool", "ok", "cache"])
TOOL_LATENCY = Histogram("vc_tool_seconds", "Tool execution time", ["tool"],
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))

GUARDRAIL_EVENTS = Counter("vc_guardrail_events_total", "Guardrail interventions", ["stage", "kind", "action"])
LLM_PROVIDER_EVENTS = Counter("vc_llm_provider_events_total", "Chuyển nhà cung cấp LLM và kiểm chứng phụ", ["event"])
AUTH_EVENTS = Counter("vc_auth_events_total", "Login attempts and rejected requests", ["event"])
RATE_LIMITED = Counter("vc_rate_limited_total", "Requests rejected by rate limiting", ["limiter"])
RAG_QUERIES = Counter("vc_rag_queries_total", "Knowledge base searches", ["hits"])


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(json_logs: bool) -> None:
    handler = logging.StreamHandler()
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def log_event(logger: logging.Logger, msg: str, **fields) -> None:
    logger.info(msg, extra={"fields": fields})


class MetricsMiddleware:
    """Đếm request theo route template (không theo id cụ thể để tránh bùng nhãn)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                route = scope.get("route")
                path = getattr(route, "path", "unmatched")
                HTTP_LATENCY.labels(path).observe(time.perf_counter() - started)
                HTTP_REQUESTS.labels(scope["method"], path, str(message["status"])).inc()
            await send(message)

        await self.app(scope, receive, send_wrapper)
