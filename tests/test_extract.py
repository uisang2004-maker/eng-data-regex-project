import pytest

from src import patterns as P
from src.collect import load_samples
from src.extract import analyze, find_acronyms, match_long_form

DEMO = ("Retrieval-augmented generation (RAG) can ground language models in external documents, but selecting "
        "reliable evidence remains challenging. To address this issue, we introduce a lightweight reranking module "
        "that scores retrieved passages using contextual relevance. Experiments on three public benchmarks show that "
        "the proposed module significantly improves retrieval precision by 8.4% compared with the baseline. These "
        "findings suggest that a compact reranker may help smaller models use evidence more consistently [4].")


# ---------------------------------------------------------------- 약어 (P0-3)

@pytest.mark.parametrize("text,abbr,expected", [
    ("We use a Gated Recurrent Unit (GRU) here.", "GRU", "Gated Recurrent Unit"),
    ("You Only Look Once (YOLO) detects objects.", "YOLO", "You Only Look Once"),
    ("We apply Low-Rank Adaptation (LoRA) to it.", "LoRA", "Low-Rank Adaptation"),
    ("Retrieval-Augmented Generation (RAG) helps.", "RAG", "Retrieval-Augmented Generation"),
    ("Bidirectional Encoder Representations from Transformers (BERT) is used.", "BERT",
     "Bidirectional Encoder Representations from Transformers"),
    ("Chain-of-Thought (CoT) prompting works.", "CoT", "Chain-of-Thought"),
    ("Large language models (LLMs) are big.", "LLM", "Large language models"),
])
def test_acronym_success(text, abbr, expected):
    assert find_acronyms(text)[abbr] == expected


@pytest.mark.parametrize("text,abbr", [
    ("Extreme Gradient Boosting (XGBoost) is strong.", "XGBoost"),
    ("A Bidirectional LSTM (BiLSTM) encoder.", "BiLSTM"),
    ("k-nearest neighbors (k-NN) is simple.", "NN"),
])
def test_acronym_failure_does_not_invent(text, abbr):
    assert find_acronyms(text).get(abbr) is None


def test_all_letters_retry_only_when_needed():
    assert match_long_form("CoT", "Chain-of-Thought ") is None
    assert match_long_form("CoT", "Chain-of-Thought ", all_letters=True) == "Chain-of-Thought"


def test_bare_acronym_marked_as_missing():
    a = analyze("GPU memory is limited. We test it.")
    assert a.acronyms == {"GPU": None}
    assert any(m.category == "abbr-missing" for m in a.marks)


# ---------------------------------------------------------------- 추측·확신·참조 (P0-4)

def marked(text, active=None, category="hedge"):
    a = analyze(text, active)
    return [a.text[m.start:m.end] for m in a.marks if m.category == category]


@pytest.mark.parametrize("text,hit", [
    ("The gains may not necessarily reflect real use.", "may"),
    ("These findings suggest a link.", "suggest"),
    ("The model seems to overfit.", "seems to"),
    ("This is likely due to noise.", "likely"),
])
def test_hedge_positive(text, hit):
    assert hit in marked(text)


@pytest.mark.parametrize("text", [
    "The method may be applied to images.",
    "It could also be easily extended to speech.",
    "The tool can be used offline.",
])
def test_hedge_exclusion(text):
    assert marked(text) == []


def test_hedge_exclusion_toggle_off_marks_again():
    active = P.DEFAULT_ACTIVE_RULES - {"HEDGE_EXCLUDE"}
    assert marked("The method may be applied to images.", active) == ["may"]


def test_hedge_case_insensitive():
    assert marked("May this hold? Perhaps.") == ["May", "Perhaps"]


def test_confident_and_reference():
    assert marked("We demonstrate state-of-the-art results.", category="confident") == ["demonstrate", "state-of-the-art"]
    assert marked("As in [3, 5] and (Smith et al., 2021), see Table 2 and Eq. (4).", category="reference") == [
        "[3, 5]", "(Smith et al., 2021)", "Table 2", "Eq. (4)"]


def test_rule_off_removes_marks():
    a = analyze(DEMO, P.DEFAULT_ACTIVE_RULES - {"ABBR", "REFERENCE"})
    assert not any(m.category in ("abbr", "reference") for m in a.marks)
    assert a.counts["abbr"] == 0 and a.counts["reference"] == 0


def test_demo_counts():
    assert analyze(DEMO).counts == {"abbr": 1, "hedge": 2, "confident": 2, "reference": 1}


# ---------------------------------------------------------------- 3줄 뼈대 (P0-2)

def card(a, kind):
    return next(c for c in a.skeleton if c.kind == kind)


def test_demo_skeleton_all_signals():
    a = analyze(DEMO)
    assert [(c.kind, c.sentence_idx, c.basis) for c in a.skeleton] == [
        ("problem", 0, "signal"), ("method", 1, "signal"), ("result", 2, "signal")]
    s = a.sentences[1].text
    c = card(a, "method")
    assert s[c.signal[0]:c.signal[1]] == "we introduce"
    assert c.reason


def test_contrast_second_sentence_is_problem():
    a = analyze("Recent advances in large models have shown success. However, they are costly to run. "
                "We propose a pruning method. It reduces memory by 40%.")
    assert card(a, "problem").sentence_idx == 1
    assert card(a, "problem").basis == "signal"


def test_new_contrast_words_are_problem_signals():
    for w in ("Despite progress, errors persist.", "Although useful, it is slow.", "Unfortunately, data is scarce."):
        assert P.SK_PROBLEM.search(w)


def test_fallback_labels_and_exclusions():
    a = analyze("Speech systems are common in phones. Many users rely on them daily. "
                "The new system reached 92 points on the test. Future work will cover other languages. "
                "Code is available at https://github.com/x/y.")
    p, m, r = (card(a, k) for k in ("problem", "method", "result"))
    assert (p.basis, p.label, p.sentence_idx) == ("position", "분야 배경 (첫 문장)", 0)
    assert m.basis == "none" and m.label == "방법 문장을 찾지 못함"
    assert r.basis == "position" and r.label == "마무리 문장 (결과 추정)"
    assert "Code is available" not in a.sentences[r.sentence_idx].text
    assert "Future work" not in a.sentences[r.sentence_idx].text
    assert 3 in a.limit_idx


def test_method_fallback_uses_author_voice():
    # "our system"은 방법 신호 문구라서, 신호에 없는 "our tokenizer"로 위치 대체를 확인한다.
    a = analyze("Translation quality varies widely. Our tokenizer uses a small vocabulary. It is fast.")
    m = card(a, "method")
    assert m.basis == "position" and m.sentence_idx == 1


def test_fallback_toggle_off():
    a = analyze("Speech systems are common. Many users rely on them.", P.DEFAULT_ACTIVE_RULES - {"SK_FALLBACK"})
    assert all(c.basis == "none" for c in a.skeleton)


def test_samples_never_produce_blank_cards():
    for r in load_samples():
        for c in analyze(r["abstract"]).skeleton:
            assert c.label and c.reason
            assert (c.sentence_idx is None) == (c.basis == "none")
