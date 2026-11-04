"""공개 사이트의 번역 사용 제한."""

from src import usage


def test_request_too_long(tmp_path):
    msg = usage.check(usage.MAX_CHARS_PER_REQUEST + 1, 0, tmp_path / "u.json")
    assert msg and "한 번에" in msg


def test_session_limit(tmp_path):
    assert usage.check(100, usage.MAX_CALLS_PER_SESSION - 1, tmp_path / "u.json") is None
    assert "번까지" in usage.check(100, usage.MAX_CALLS_PER_SESSION, tmp_path / "u.json")


def test_daily_cap_counts_and_blocks(tmp_path):
    path = tmp_path / "u.json"
    usage.record(usage.DAILY_CHAR_CAP - 500, path)
    assert usage.used_today(path) == usage.DAILY_CHAR_CAP - 500
    assert usage.check(400, 0, path) is None
    assert "오늘" in usage.check(600, 0, path)


def test_new_day_resets(tmp_path):
    path = tmp_path / "u.json"
    path.write_text('{"date": "2000-01-01", "chars": 999999}', encoding="utf-8")
    assert usage.used_today(path) == 0 and usage.check(100, 0, path) is None


def test_meaning_requests_skip_per_request_limit(tmp_path):
    path = tmp_path / "u.json"
    assert usage.check(10_000, 0, path, engine="claude") is not None
    assert usage.check(10_000, 0, path, engine="claude", per_request=False) is None
    assert "번까지" in usage.check(10_000, 60, path, engine="claude", per_request=False)
