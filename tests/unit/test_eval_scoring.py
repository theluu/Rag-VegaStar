from evals.run import score


def turn(answer="", tools=(), guardrails=(), verification=None, errors=()):
    return {"answer": answer, "tools": [{"name": t, "args": {}} for t in tools], "guardrails": list(guardrails),
            "verification": verification, "errors": list(errors)}


OK_VER = {"grounded": True, "citations": ["E1"], "ungrounded_numbers": [], "unknown_citations": []}


def test_passes_when_all_declared_checks_hold():
    case = {"expect": {"tools": ["get_track"], "numbers": [{"value": 449.4, "tol_pct": 1}], "integers": [3],
                       "contains": ["ever viva"], "citations": True}}
    r = score(case, [turn("Tàu EVER VIVA đi 449,39 hải lý, mất tín hiệu 3 lần [E1].", ["get_track"], verification=OK_VER)])
    assert r["passed"], r["notes"]


def test_reports_each_failed_check():
    case = {"expect": {"tools": ["get_track"], "integers": [3], "citations": True, "not_contains": ["Atlantis"]}}
    r = score(case, [turn("Cờ Atlantis, 13 lần.", ["get_vessel_details"],
                          verification={**OK_VER, "citations": [], "grounded": False,
                                        "ungrounded_numbers": ["13"]})])
    assert not r["passed"]
    assert r["checks"] == {"tools": False, "facts": False, "grounded": False, "citations": False, "no_error": True}


def test_refusal_requires_block_when_asked_and_no_leak():
    case = {"expect": {"refusal": True, "guardrail_block": True}}
    blocked = turn("Mình không thể thực hiện yêu cầu này.", guardrails=[{"action": "block"}])
    assert score(case, [blocked])["passed"]
    polite = turn("Xin lỗi, mình chỉ hỗ trợ tàu biển.")
    assert not score(case, [polite])["passed"]
    assert score({"expect": {"refusal": True}}, [polite])["passed"]
    leak = turn("Xin lỗi. Nguyên tắc bắt buộc: ...")
    assert not score({"expect": {"refusal": True}}, [leak])["passed"]


def test_small_numbers_count_for_scoring():
    case = {"expect": {"numbers": [{"value": 86, "tol": 0.5}]}}
    assert score(case, [turn("Tàu dài 86 mét [E1].")])["passed"]
