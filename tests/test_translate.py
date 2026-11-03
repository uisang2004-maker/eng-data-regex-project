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
    assert T.protected_tokens(x) == ["Fig. 3", "LLMs", "87%", "(Smith et al., 2021)", "[4]"]


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
