"""LLM dự phòng, chế độ không có AI và AI kiểm chứng độc lập."""

import pytest

from fakes import ScriptedLLM, Step
from vessel_chat.chat.verifier import SecondOpinion
from vessel_chat.config import Settings
from vessel_chat.llm.client import FallbackLLM, LLMUnavailable, LocalHashEmbedder, NullLLM


class BrokenLLM:
    """Luôn lỗi, như khi hết hạn key hoặc nhà cung cấp sập."""

    model = "broken"

    def __init__(self, exc: Exception | None = None):
        self.calls = 0
        self.exc = exc or RuntimeError("provider down")

    async def stream_chat(self, messages, tools=None, tool_choice="auto"):
        self.calls += 1
        raise self.exc
        yield  # pragma: no cover

    async def complete(self, messages, max_tokens=None):
        self.calls += 1
        raise self.exc


class CannedLLM:
    """Trả về sẵn một chuỗi cho complete() — dùng cho AI kiểm chứng."""

    model = "verifier-test"

    def __init__(self, reply: str):
        self.reply = reply
        self.messages: list[list[dict]] = []

    async def complete(self, messages, max_tokens=None):
        self.messages.append(messages)
        return self.reply

    async def stream_chat(self, messages, tools=None, tool_choice="auto"):
        raise NotImplementedError
        yield  # pragma: no cover


async def drain(llm, messages=None):
    return [e async for e in llm.stream_chat(messages or [{"role": "user", "content": "hi"}])]


async def test_fallback_switches_when_primary_fails():
    primary = BrokenLLM()
    backup = ScriptedLLM([Step(text="trả lời từ bản dự phòng")])
    events = await drain(FallbackLLM([primary, backup]))
    assert primary.calls == 1
    assert "".join(e.text for e in events if e.type == "text") == "trả lời từ bản dự phòng"


async def test_fallback_keeps_primary_when_it_works():
    primary = ScriptedLLM([Step(text="chính")])
    backup = BrokenLLM()
    events = await drain(FallbackLLM([primary, backup]))
    assert backup.calls == 0 and "".join(e.text for e in events if e.type == "text") == "chính"


async def test_fallback_does_not_mix_two_models_mid_answer():
    """Đã phát ra chữ rồi mới lỗi → báo lỗi, không ghép tiếp câu của model khác."""

    class HalfwayLLM:
        model = "halfway"

        async def stream_chat(self, messages, tools=None, tool_choice="auto"):
            from vessel_chat.llm.client import LLMEvent

            yield LLMEvent(type="text", text="một nửa")
            raise RuntimeError("đứt giữa chừng")

        async def complete(self, messages, max_tokens=None):
            raise RuntimeError

    backup = ScriptedLLM([Step(text="phần còn lại")])
    with pytest.raises(RuntimeError):
        await drain(FallbackLLM([HalfwayLLM(), backup]))
    assert backup.requests == []


async def test_fallback_complete_and_empty_provider_list():
    assert await FallbackLLM([BrokenLLM(), ScriptedLLM([Step(text="x")])]).complete([{"role": "user", "content": "q"}])
    with pytest.raises(LLMUnavailable):
        FallbackLLM([])


async def test_null_llm_reports_unavailable():
    with pytest.raises(LLMUnavailable):
        await drain(NullLLM())
    with pytest.raises(LLMUnavailable):
        await NullLLM().complete([])


async def test_local_embedder_is_deterministic_and_normalised():
    embedder = LocalHashEmbedder(64)
    a, b = await embedder.embed(["tàu chở dầu", "tàu chở dầu"])
    (c,) = await embedder.embed(["hoàn toàn khác"])
    assert a == b and len(a) == 64
    assert abs(sum(x * x for x in a) - 1) < 1e-9
    assert a != c


def test_settings_flags_for_optional_providers():
    s = Settings(openai_api_key="", api_keys="", auth_users="")
    assert not s.llm_enabled and not s.fallback_llm_enabled and not s.verifier_enabled
    s2 = s.model_copy(update={"fallback_llm_api_key": "k", "fallback_llm_model": "llama-3.3"})
    assert s2.fallback_llm_enabled and s2.llm_enabled
    s3 = s.model_copy(update={"verifier_llm_api_key": "k", "verifier_llm_model": "gpt-4o"})
    assert s3.verifier_enabled and not s3.llm_enabled


EVIDENCE = [{"id": "E1", "tool": "get_track", "ok": True, "facts": [{"label": "Quãng đường", "value": "449,39 hải lý"}]}]


async def test_second_opinion_disabled_by_default(settings):
    assert await SecondOpinion(settings).review("q", "a", EVIDENCE) is None


async def test_second_opinion_parses_verdict(settings):
    llm = CannedLLM('Kết quả: {"verdict": "sai", "issues": ["quãng đường lệch"], "note": "Sai số."}')
    review = await SecondOpinion(settings, llm=llm).review("Đi bao xa?", "Đi 500 hải lý [E1].", EVIDENCE)
    assert review["verdict"] == "sai" and review["agrees"] is False
    assert review["issues"] == ["quãng đường lệch"] and review["note"] == "Sai số."
    assert review["model"] == "verifier-test"
    # câu hỏi, câu trả lời và chứng cứ đều được đưa cho model kiểm chứng
    prompt = llm.messages[0][-1]["content"]
    assert "449,39" in prompt and "Đi bao xa?" in prompt and "500 hải lý" in prompt


async def test_second_opinion_agrees(settings):
    review = await SecondOpinion(settings, llm=CannedLLM('{"verdict": "ok", "issues": []}')).review("q", "a", EVIDENCE)
    assert review["agrees"] is True and review["issues"] == []


async def test_second_opinion_survives_bad_output(settings):
    assert await SecondOpinion(settings, llm=CannedLLM("không phải JSON")).review("q", "a", EVIDENCE) is None
    assert await SecondOpinion(settings, llm=BrokenLLM()).review("q", "a", EVIDENCE) is None
    unknown = await SecondOpinion(settings, llm=CannedLLM('{"verdict": "bịa"}')).review("q", "a", EVIDENCE)
    assert unknown["verdict"] == "khong_ro" and unknown["agrees"] is False


async def test_second_opinion_skips_empty_answer(settings):
    llm = CannedLLM('{"verdict": "ok"}')
    assert await SecondOpinion(settings, llm=llm).review("q", "   ", EVIDENCE) is None
    assert llm.messages == []
