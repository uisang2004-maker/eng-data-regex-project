"""단어표 AI 풀이 테스트(가짜 클라이언트, 네트워크 없음)."""

import json
from types import SimpleNamespace as NS

import pytest

from src import explain as X
from src import glossary as G
from src import translate as T
from src.extract import analyze


class FakeClaude:
    def __init__(self, text):
        self.calls, outer = [], self

        class Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                return NS(stop_reason="end_turn", content=[NS(type="text", text=text)])

        self.messages = Messages()


ITEMS = [("reranker", "A compact reranker may help.", ""), ("RAG", "RAG can ground models.", "Retrieval-augmented generation")]


def test_request_uses_json_schema_and_context():
    fc = FakeClaude(json.dumps({"items": [{"term": "reranker", "meaning": "검색 결과 순위를 다시 매기는 모델"}]}))
    out = X.explain_terms(ITEMS, "k", client=fc)
    assert out == {"reranker": "검색 결과 순위를 다시 매기는 모델"}
    kw = fc.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["effort"] == "low"
    assert kw["model"] == "claude-haiku-5-5"
    body = kw["messages"][0]["content"]
    assert "A compact reranker may help." in body and "Retrieval-augmented generation" in body


def test_only_requested_terms_kept_and_trimmed():
    fc = FakeClaude(json.dumps({"items": [{"term": "unknown", "meaning": "지어낸 단어"},
                                          {"term": "RAG", "meaning": "가" * 200}, {"term": "reranker", "meaning": ""}]}))
    out = X.explain_terms(ITEMS, "k", client=fc)
    assert set(out) == {"RAG"} and len(out["RAG"]) == X.MAX_MEANING and out["RAG"].endswith("…")


def test_bad_json_is_error_and_empty_input_skips_call():
    with pytest.raises(T.TranslationError):
        X.explain_terms(ITEMS, "k", client=FakeClaude("not json"))
    fc = FakeClaude("{}")
    assert X.explain_terms([], "k", client=fc) == {} and fc.calls == []


def test_request_caps_terms():
    many = [(f"term{i}", "s", "") for i in range(X.MAX_TERMS + 10)]
    assert X.build_request(many).count("- term:") == X.MAX_TERMS


def test_glossary_items_csv_and_apply():
    a = analyze("Retrieval-augmented generation (RAG) helps. A compact reranker may help smaller models.")
    rows = G.build(a)
    items = G.ai_items(a, rows)
    assert ("RAG", a.sentences[0].text, "Retrieval-augmented generation") in items
    G.apply_ai(rows, {"RAG": "검색 증강 생성"})
    csv = G.to_csv(rows).decode("utf-8-sig")
    assert "AI 풀이(참고용)" in csv and "검색 증강 생성" in csv
