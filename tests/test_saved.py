"""번역 결과 저장 형식(브라우저 저장·결과 파일) 테스트."""

import json

import pytest

from src import saved as SV
from src.translate import TranslationResult


def sample():
    tr = TranslationResult(ko=["가 나다.", "라 마."], mode="aligned", ko_marks=[[(0, 1, "term", "A")], []],
                           ko_underlines=[[(0, 3, "method")], []], protected=[["RAG"], []])
    off = TranslationResult(ko=None, mode="none", error="실패")      # 실패한 번역은 저장하지 않는다
    return {("k1", True): tr, ("k1", False): off}, {"k1": {"reranker": "재순위 모델"}, "k2": {}}


def test_pack_and_unpack_round_trip():
    translations, gloss = sample()
    items = SV.pack_items(translations, gloss, now=100)
    assert set(items) == {"k1"} and set(items["k1"]["t"]) == {"1"}
    back_t, back_g = SV.unpack_items(json.loads(json.dumps(items)))      # JSON을 한 번 거쳐도 같아야 한다
    r = back_t[("k1", True)]
    assert r.ko == ["가 나다.", "라 마."] and r.ko_marks[0] == [(0, 1, "term", "A")] and r.cached
    assert r.ko_underlines[0] == [(0, 3, "method")] and back_g == {"k1": {"reranker": "재순위 모델"}}


def test_signature_changes_when_meanings_added():
    translations, _ = sample()
    a = SV.pack_items(translations, {})["k1"]
    b = SV.pack_items(translations, {"k1": {"x": "y"}})["k1"]
    assert SV.signature(a) != SV.signature(b)


def test_file_round_trip_and_bad_files():
    translations, gloss = sample()
    data = SV.to_file(SV.pack_items(translations, gloss), "제목")
    assert set(SV.from_file(data)) == {"k1"}
    with pytest.raises(ValueError):
        SV.from_file(b"not json")
    with pytest.raises(ValueError):
        SV.from_file(json.dumps({"format": "other", "items": {}}).encode())


def test_trim_drops_oldest_first():
    items = {f"k{i}": {"t": {}, "g": {"w": "x" * 200}, "ts": i} for i in range(10)}
    kept = SV.trim(items, max_bytes=1000)
    assert "k9" in kept and "k0" not in kept
    assert len(json.dumps(kept, ensure_ascii=False).encode()) <= 1000


def test_broken_items_are_skipped():
    t, g = SV.unpack_items({"a": {"t": {"1": {"nonsense": 1}}}, "b": "x", "c": {"g": {"w": "뜻"}}})
    assert t == {} and g == {"c": {"w": "뜻"}}


def test_doc_record_is_stable_and_valid():
    secs = [{"title": "Abstract", "text": "We propose X."}, {"title": "1 Introduction", "text": "X is new.", "subheads": []}]
    a = SV.doc_record("pdf", "Paper", secs, {"notes": ["n"]}, now=1)
    b = SV.doc_record("pdf", "Paper", secs, now=2)
    assert a["id"] == b["id"] and SV.valid_doc(a) and a["notes"] == ["n"]
    assert not SV.valid_doc({"kind": "pdf", "sections": [{"title": "x"}]})        # 글이 없는 절
    assert SV.text_hash("abc") == SV.text_hash("abc") and len(SV.text_hash("abc")) == 16


def test_file_carries_documents():
    rec = SV.doc_record("paste", "글", [{"title": "붙여 넣은 글", "text": "We test."}])
    data = SV.to_file({}, "t", {rec["id"]: rec, "bad": {"kind": "x"}})
    assert set(SV.docs_from_file(data)) == {rec["id"]}
    assert SV.docs_from_file(b"{}") == {} and SV.docs_from_file(b"not json") == {}
