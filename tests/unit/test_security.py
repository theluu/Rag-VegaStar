from vessel_chat.api.security import RateLimiter, key_matches


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_rate_limiter_allows_burst_then_blocks():
    clock = FakeClock()
    rl = RateLimiter(per_minute=3, clock=clock)
    assert [rl.check("a")[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after = rl.check("a")
    assert allowed is False and 0 < retry_after <= 20
    # khoá khác không bị ảnh hưởng
    assert rl.check("b")[0] is True


def test_rate_limiter_refills_over_time():
    clock = FakeClock()
    rl = RateLimiter(per_minute=6, clock=clock)
    for _ in range(6):
        rl.check("a")
    assert rl.check("a")[0] is False
    clock.now += 10  # 6/phút → 1 token mỗi 10 giây
    assert rl.check("a")[0] is True
    assert rl.check("a")[0] is False


def test_rate_limiter_disabled_when_zero():
    rl = RateLimiter(per_minute=0)
    assert all(rl.check("a")[0] for _ in range(100))


def test_rate_limiter_evicts_idle_buckets():
    clock = FakeClock()
    rl = RateLimiter(per_minute=2, clock=clock, max_keys=2)
    rl.check("a")
    clock.now += 1
    rl.check("b")
    clock.now += 1
    rl.check("c")
    assert len(rl._buckets) == 2 and "a" not in rl._buckets


def test_key_matches_constant_time_compare():
    assert key_matches("s3cret", ["other", "s3cret"]) is True
    assert key_matches("s3cre", ["s3cret"]) is False
    assert key_matches(None, ["s3cret"]) is False
    assert key_matches("", ["s3cret"]) is False
