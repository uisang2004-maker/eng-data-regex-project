import re

import pytest

from src import translate as T
from src.collect import load_samples
from src.extract import analyze


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "CACHE_PATH", tmp_path / "cache.json")


def fake_ok(texts, key, split):
    """태그를 그대로 두고 문장마다 'KO:'를 붙이는 가짜 번역기."""
    return [re.sub(r"<s>", "<s>KO:", t) if split == "nonewlines" else "KO:" + t for t in texts]


# ---------------------------------------------------------------- 마스킹

def test_protect_roundtrip_on_samples():
    for r in load_samples()[:100]:
        a = analyze(r["abstract"])
        for s in a.sentences:
            assert T.unprotect(T.protect(s.text, a.acronyms)) == s.text


def test_protect_tokens():
    x = T.protect("As shown in Fig. 3, LLMs reach 87% (Smith et al., 2021) [4].", {"LLM": "x"})
    assert T.protected_tokens(x) == ["Fig. 3", "LLMs", "(Smith et al., 2021)", "[4]"]


def test_numbers_are_not_protected():
    """실측(2026-11-04)에서 수치를 가리면 DeepL이 수치를 뒤섞어서, 수치는 보호하지 않는다."""
    x = T.protect("Ours reaches 72.3% while the baseline reaches 67.9%.")
    assert "<x>" not in x


def test_protect_escapes_xml():
    assert T.protect("a < b & c") == "a &lt; b &amp; c"


@pytest.mark.parametrize("raw,fixed", [
    ("(제Section 5.1)", "(Section 5.1)"),
    ("BERT 는 강하다", "BERT는 강하다"),
    ("수 있다 [4].", "수 있다[4]."),
    ("(Table 2) 이 방법은", "(Table 2) 이 방법은"),
])
def test_fix_korean(raw, fixed):
    assert T.fix_korean(raw) == fixed


# ---------------------------------------------------------------- 정렬·안전장치

def test_aligned_with_sentence_tags():
    r = T.translate(["One.", "Two [4]."], caller=fake_ok, api_key="k")
    assert r.mode == "aligned" and r.ko == ["KO:One.", "KO:Two [4]."]   # 영어 뒤 공백은 그대로(한국어 뒤만 정리)
    assert T.preserved_ratio(r) == (1, 1)


def test_broken_tags_fall_back_to_per_sentence():
    calls = []

    def fake(texts, key, split):
        calls.append(split)
        return ["태그가 사라진 번역"] if split == "nonewlines" else ["가", "나"]

    r = T.translate(["One.", "Two."], caller=fake, api_key="k")
    assert calls == ["nonewlines", "0"] and r.mode == "per_sentence" and r.ko == ["가", "나"]


def test_count_mismatch_falls_back_to_paragraph():
    def fake(texts, key, split):
        return ["<s>가</s>"] if split == "nonewlines" else ["하나뿐"]

    r = T.translate(["One.", "Two."], caller=fake, api_key="k")
    assert r.mode == "paragraph" and r.ko is None and r.paragraph == "가"


@pytest.mark.parametrize("code,word", [(429, "잠시"), (456, "한도"), (403, "키")])
def test_http_errors_do_not_raise(code, word):
    def fake(texts, key, split):
        raise T.TranslationError(T.ERROR_MESSAGES[code], code)

    r = T.translate(["One."], caller=fake, api_key="k")
    assert r.ko is None and word in r.error


def test_no_key(monkeypatch):
    monkeypatch.setattr(T, "load_api_key", lambda: None)
    r = T.translate(["One."], caller=fake_ok)
    assert r.ko is None and r.error == T.NO_KEY_MESSAGE


def test_cache_prevents_second_call():
    n = {"calls": 0}

    def fake(texts, key, split):
        n["calls"] += 1
        return fake_ok(texts, key, split)

    T.translate(["One."], caller=fake, api_key="k")
    second = T.translate(["One."], caller=fake, api_key="k")
    assert n["calls"] == 1 and second.cached


def test_masked_and_unmasked_are_cached_separately():
    a = T.translate(["BERT works."], {"BERT": None}, masked=True, caller=fake_ok, api_key="k")
    b = T.translate(["BERT works."], {"BERT": None}, masked=False, caller=fake_ok, api_key="k")
    assert not a.cached and not b.cached


def test_split_error_does_not_spread():
    """문장이 잘못 끊겨도 다른 문장의 짝은 밀리지 않는다(문장마다 태그로 짝지음)."""
    r = T.translate(["Half one", "half two.", "Next sentence."], caller=fake_ok, api_key="k")
    assert r.ko[2] == "KO:Next sentence."


# ---------------------------------------------------------------- 한국어 형광펜(표시 태그)

def test_to_xml_wraps_marks():
    s = "RAG may help [4]."
    marks = [(0, 3, "abbr"), (4, 7, "hedge"), (13, 16, "reference")]
    x = T.to_xml(s, {"RAG": "Retrieval-augmented generation"}, masked=True, marks=marks)
    assert x == '<x c="abbr" i="0">RAG</x> <m c="hedge" i="1">may</m> help <x c="reference" i="2">[4]</x>.'


def test_unmasked_without_marks_is_plain_escape():
    """마크가 없으면 예전과 같은 XML이라, 이전 실측의 마스킹 끔 캐시가 그대로 맞는다."""
    assert T.to_xml("a < b [4]", masked=False) == "a &lt; b [4]"


def test_unmasked_marks_use_m_tags():
    x = T.to_xml("See Table 2.", masked=False, marks=[(4, 11, "reference")])
    assert x == 'See <m c="reference" i="0">Table 2</m>.'


def test_ko_marks_follow_moved_tags():
    def fake(texts, key, split):
        return ['<s>이 결과는 도움이 될 <m c="hedge" i="0">수</m> 있음을 <m c="hedge" i="1">시사한다</m> '
                '<x c="reference" i="2">[4]</x>.</s>']

    s = "These findings suggest it may help [4]."
    marks = [(26, 29, "hedge"), (15, 22, "hedge"), (35, 38, "reference")]
    r = T.translate([s], {}, marks=[marks], caller=fake, api_key="k")
    assert r.ko == ["이 결과는 도움이 될 수 있음을 시사한다[4]."]
    got = [(r.ko[0][a:b], c, en) for a, b, c, en in r.ko_marks[0]]
    assert got == [("수", "hedge", "may"), ("시사한다", "hedge", "suggest"), ("[4]", "reference", "[4]")]


def test_lost_tag_is_dropped_without_error():
    def fake(texts, key, split):
        return ["<s>반드시 반영하는 것은 아니다.</s>"]

    r = T.translate(["It may not necessarily reflect use."], {}, marks=[[(3, 6, "hedge")]], caller=fake, api_key="k")
    assert r.ko == ["반드시 반영하는 것은 아니다."] and r.ko_marks == [[]]


def test_ko_marks_survive_file_cache():
    def fake(texts, key, split):
        return ['<s><m c="confident" i="0">크게</m> 향상됨.</s>']

    args = (["It greatly improves."], {})
    first = T.translate(*args, marks=[[(3, 10, "confident")]], caller=fake, api_key="k")
    second = T.translate(*args, marks=[[(3, 10, "confident")]], caller=fake, api_key="k")
    assert second.cached and second.ko_marks == first.ko_marks == [[(0, 2, "confident", "greatly")]]


# ---------------------------------------------------------------- 핵심 내용 밑줄

def test_to_xml_underline_wraps_and_does_not_cut_tags():
    s = "We introduce a compact RAG reranker [4]."
    x = T.to_xml(s, {"RAG": "x"}, masked=True, marks=[(23, 26, "abbr")], underline=(13, 27, "method"))
    # 밑줄 끝(27)이 'reranker' 중간이 아니라 태그 밖에 놓이고, <x>는 <u> 안에 통째로 들어간다
    assert x.startswith('We introduce <u c="u-method" i="0">a compact <x c="abbr" i="0">RAG</x>')
    assert x.count("<u ") == 1 and x.count("</u>") == 1


def test_ko_underline_picks_longest_piece_and_trims_particle():
    raw = '우리는 <u c="u-method" i="0">간결한 재순위 지정기를</u> 소개한다<u c="u-method" i="0">.</u>'
    plain = T.fix_korean(T.unprotect(raw))
    a, b, kind = T.ko_underline_from_xml(raw, plain)
    assert plain[a:b] == "간결한 재순위 지정기" and kind == "method"


def test_ko_underline_keeps_noun_final_syllables():
    raw = '<u c="u-result" i="0">성능 평가</u>가 좋아졌다.'
    plain = T.fix_korean(T.unprotect(raw))
    a, b, _ = T.ko_underline_from_xml(raw, plain)
    assert plain[a:b] == "성능 평가"


def test_unclosed_tags_do_not_leak_into_text():
    raw = '모델 <u c="u-result" i="0">높은 정밀도를 <x c="abbr" i="1">BERT</x> 달성합니다.'
    plain = T.fix_korean(T.unprotect(raw))
    assert "<" not in plain and T.ko_underline_from_xml(raw, plain) is None


def test_translate_returns_ko_underlines():
    def fake(texts, key, split):
        return ['<s>그러나 <u c="u-problem" i="0">증거 선별은 여전히 어렵다</u>.</s>']

    r = T.translate(["However, selecting evidence remains hard."], {}, underlines=[(9, 40, "problem")],
                    caller=fake, api_key="k")
    [(a, b, kind)] = r.ko_underlines[0]
    assert r.ko[0][a:b] == "증거 선별은 여전히 어렵다" and kind == "problem"


def test_ko_underline_extends_to_word_end_without_cutting_endings():
    raw = '검색 정확도를 <u c="u-result" i="0">8.4%나 크게 향상시키</u>는 것으로 나타났다.'
    plain = T.fix_korean(T.unprotect(raw))
    a, b, _ = T.ko_underline_from_xml(raw, plain)
    assert plain[a:b] == "8.4%나 크게 향상시키는"


def test_cache_recomputes_from_raw_without_calling_again():
    n = {"calls": 0}

    def fake(texts, key, split):
        n["calls"] += 1
        return ['<s>그러나 <u c="u-problem" i="0">증거 선별은 여전히 어렵다</u>.</s>']

    args = dict(underlines=[(9, 40, "problem")], caller=fake, api_key="k")
    T.translate(["However, selecting evidence remains hard."], {}, **args)
    again = T.translate(["However, selecting evidence remains hard."], {}, **args)
    assert n["calls"] == 1 and again.cached and again.ko_underlines[0]


def test_to_xml_multiple_underlines_keep_order_and_drop_overlap():
    s = "We propose GMM-LDA, a topic model, to analyze text."
    x = T.to_xml(s, masked=False, underline=[(11, 51, "method"), (20, 33, "def")])
    assert x.count("<u ") == 1 and 'c="u-method" i="0"' in x      # 겹치는 용어 설명 밑줄은 버림
    x2 = T.to_xml(s, masked=False, underline=[(20, 33, "def"), (37, 51, "method")])
    assert x2.count("<u ") == 2 and 'i="1"' in x2


def test_ko_underlines_multiple():
    raw = '<u c="u-def" i="0">주제 모델</u>인 GMM-LDA로 <u c="u-method" i="1">텍스트를 분석</u>한다.'
    plain = T.fix_korean(T.unprotect(raw))
    got = [(plain[a:b], k) for a, b, k in T.ko_underlines_from_xml(raw, plain)]
    assert got == [("주제 모델", "def"), ("텍스트를 분석한다", "method")]
