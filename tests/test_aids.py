"""이해를 돕는 자료: 흐름도(문장 역할)와 단어표."""

from src import glossary as G
from src.extract import analyze
from src.translate import TranslationResult

TEXT = ("Speech systems are common in phones. However, accents remain challenging. "
        "We propose AccentNet, a small adapter, to handle accents. "
        "Experiments show that AccentNet reduces errors by 12% on accented speech. "
        "Future work will cover more languages. Retrieval-augmented generation (RAG) is related.")


def test_roles_follow_paper_flow():
    assert analyze(TEXT).roles == ["background", "problem", "method", "result", "limit", "detail"]


def test_first_sentence_fallback_is_background():
    a = analyze("Speech systems are common. Many users rely on them. Our model reached 92 points.")
    assert a.roles[0] == "background"


def test_glossary_collects_acronyms_terms_and_explained():
    rows = {e.term: e for e in G.build(analyze(TEXT))}
    assert rows["RAG"].explanation == "Retrieval-augmented generation" and rows["RAG"].kinds == ["abbr"]
    assert rows["AccentNet"].explanation == "a small adapter" and "explained" in rows["AccentNet"].kinds
    assert rows["AccentNet"].count == 2 and rows["AccentNet"].first_sentence == 3
    assert "accent" not in rows      # accents 2번 + accented(-ed 한 단어 제외) → 3번이 안 됨


def test_glossary_korean_from_translation_tags():
    a = analyze(TEXT)
    ko = ["가"] * len(a.sentences)
    ko[2] = "우리는 악센트넷을 제안한다."
    ko[5] = "검색 증강 생성(RAG)은 관련이 있다."
    marks = [[] for _ in ko]
    marks[2] = [(4, 8, "term", "AccentNet")]
    at = ko[5].find("RAG")
    marks[5] = [(at, at + 3, "abbr", "RAG")]
    tr = TranslationResult(ko=ko, mode="aligned", ko_marks=marks)
    rows = {e.term: e for e in G.build(a, G.korean_marks(tr))}
    assert rows["AccentNet"].korean == "악센트넷"
    assert rows["RAG"].korean == ""        # 번역되지 않고 그대로 남은 약어는 한국어 칸에 넣지 않음


def test_csv_has_bom_and_header():
    data = G.to_csv(G.build(analyze(TEXT)))
    assert data.startswith("﻿".encode("utf-8")) and "용어,종류".encode("utf-8") in data


# ---------------------------------------------------------------- 어려운 단어(전문용어) 위주

def test_easy_words_are_excluded_and_rare_words_have_levels():
    t = ("A label is a sentence. The label marks each sentence. Every label and sentence matters. "
         "We use a stochastic reranker with heuristic annotation.")
    rows = {e.term.lower(): e for e in G.build(analyze(t))}
    assert "label" not in rows and "sentence" not in rows          # 일상어(Zipf 4.0 이상)
    assert rows["stochastic"].level == "중"                          # Zipf 3.11
    assert rows["heuristic"].level == "상" and rows["reranker"].level == "상"


def test_generic_academic_words_and_long_form_words_are_excluded():
    t = "We propose a method. Retrieval-augmented generation (RAG) helps retrieval."
    terms = {e.term.lower() for e in G.build(analyze(t))}
    assert "propose" not in terms and "retrieval-augmented" not in terms and "rag" in terms


def test_word_zipf_uses_base_forms():
    assert G.word_zipf("baselines") == G.word_zipf("baseline") > 0
    assert G.word_zipf("propagated") >= G.word_zipf("propagate") > 0
    assert G.word_zipf("qzxwv") == 0.0


def test_jargon_marks_are_for_translation_only():
    a = analyze("A stochastic reranker helps.")
    assert [a.text[x:y] for x, y, _ in G.jargon_marks(a)] == ["stochastic", "reranker"]
    assert not any(m.category == "jargon" for m in a.marks)
