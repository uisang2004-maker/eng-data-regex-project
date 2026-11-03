import pytest

from src import analyze as A
from src import collect as C
from src import translate as T


@pytest.mark.parametrize("raw,expected", [
    ("2402.08910", "2402.08910"),
    ("arXiv:2402.08910v2", "2402.08910v2"),
    ("  1212.6527 ", "1212.6527"),
    ("cs/0112017", "cs/0112017"),
])
def test_arxiv_id_valid(raw, expected):
    assert C.normalize_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "2402.089", "hello", "2402.08910; rm"])
def test_arxiv_id_invalid(raw):
    with pytest.raises(C.ArxivError):
        C.normalize_id(raw)


FEED = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2402.08910v1</id><published>2024-02-14T00:00:00Z</published>
<title>A  Title</title><summary> An abstract. </summary><author><name>Someone</name></author></entry></feed>"""


def test_fetch_uses_cache_and_drops_authors(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE_PATH", tmp_path / "arxiv.json")
    calls = []
    monkeypatch.setattr(C, "_get", lambda params: calls.append(params) or FEED)
    first = C.fetch_abstract("2402.08910")
    second = C.fetch_abstract("2402.08910")
    assert first["title"] == "A Title" and first["abstract"] == "An abstract." and first["year"] == 2024
    assert "author" not in first and "Someone" not in str(first)
    assert len(calls) == 1 and second["cached"]


def test_rate_limit_waits(monkeypatch):
    sleeps = []
    monkeypatch.setattr(C.time, "sleep", lambda s: sleeps.append(s))

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return FEED

    monkeypatch.setattr(C.urllib.request, "urlopen", lambda *a, **k: Resp())
    C._last_call = 0.0
    C._get({"id_list": "x"})
    C._get({"id_list": "y"})
    assert sleeps and sleeps[-1] > 2.5


def test_skeleton_stats_shape():
    rows = C.load_samples()[:20]
    s = A.skeleton_stats(rows)
    assert s["n"] == 20
    assert s["with_fallback"]["all_three_filled"] >= s["signal_only"]["all_three_filled"]


def test_masking_benchmark_with_fake(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "CACHE_PATH", tmp_path / "cache.json")

    def fake(texts, key, split):   # 마스킹 끔이면 숫자를 지워 버리는 가짜 번역기
        out = []
        for t in texts:
            out.append(t if "<x>" in t else __import__("re").sub(r"\d", "", t))
        return out

    res = A.masking_benchmark(C.load_samples(), n=3, caller=fake, api_key="k")
    s = res["summary"]
    assert s["papers"] == 3 and s["on_kept"] >= s["off_kept"]
