from pydantic import BaseModel, Field

from ..observability import RAG_QUERIES
from ..rag.store import search
from .base import Tool, ToolContext, ToolResult, error_result, register

TEXT_MAX_CHARS = 1000


@register
class SearchKnowledge(Tool):
    name = "search_knowledge"
    description = (
        "Tra kho tri thức nghiệp vụ hàng hải và tài liệu hệ thống: ý nghĩa trạng thái hành hải AIS, mã và nhóm "
        "loại tàu, MMSI/IMO/hô hiệu, vai trò chủ sở hữu và quản lý, dark gap (định nghĩa, nguyên nhân, cách "
        "diễn giải), đơn vị đo (hải lý, knot, DWT, GT, mớn nước), phạm vi và chất lượng bộ dữ liệu, cách dùng "
        "hệ thống. Dùng cho câu hỏi 'là gì / nghĩa là gì / vì sao / cách hiểu'. KHÔNG dùng để tra số liệu của "
        "một tàu cụ thể (hãy dùng các tool dữ liệu)."
    )

    class Args(BaseModel):
        query: str = Field(min_length=2, max_length=300, description="Câu hỏi hoặc từ khoá cần tra")

    async def run(self, ctx: ToolContext, args: Args) -> ToolResult:
        if ctx.embedder is None:
            return error_result("Kho tri thức chưa sẵn sàng")
        s = ctx.settings
        async with ctx.pool.acquire() as conn:
            hits = await search(conn, ctx.embedder, args.query, k=s.rag_top_k,
                                candidates=s.rag_candidates, min_score=s.rag_min_score)
        RAG_QUERIES.labels("yes" if hits else "no").inc()
        if not hits:
            return ToolResult(content={
                "status": "no_results",
                "query": args.query,
                "message": "Kho tri thức không có nội dung liên quan; không được tự suy đoán.",
            })
        return ToolResult(content={
            "status": "ok",
            "query": args.query,
            "results": [
                {
                    "citation": f"{h['source']} › {h['section']}",
                    "text": h["content"][:TEXT_MAX_CHARS],
                    "relevance": round(float(h["score"]), 3),
                    "matched_keywords": h["keyword_rank"] is not None,
                }
                for h in hits
            ],
        })
