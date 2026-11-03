from src.clean import clean, split_sentences


def sentences(text):
    t = clean(text).text
    return [t[s:e] for s, e in split_sentences(t)]


# ---------------------------------------------------------------- 최소 방어선 5종

def test_soft_newline_and_spaces():
    assert clean("Large language\nmodels   are   useful.").text == "Large language models are useful."


def test_dehyphen():
    assert clean("domain-specific termi-\nnology").text == "domain-specific terminology"


def test_page_number_line_removed_without_breaking_paragraph():
    r = clean("The model works\n12\nwell in practice.")
    assert r.text == "The model works well in practice."
    assert "12" in r.removed_lines


def test_repeated_header_removed():
    raw = "Journal of Tests\nFirst part.\nJournal of Tests\nSecond part.\nJournal of Tests\nThird part."
    r = clean(raw)
    assert "Journal of Tests" not in r.text
    assert r.text == "First part. Second part. Third part."
    assert r.removed_lines == ["Journal of Tests"]


def test_header_repeated_twice_is_kept():
    assert "Short line" in clean("Short line\nA.\nShort line\nB.").text


def test_curly_quotes_normalized():
    assert clean("We don’t know.").text == "We don't know."


def test_paragraph_break_kept():
    assert clean("First paragraph.\n\nSecond paragraph.").text == "First paragraph.\n\nSecond paragraph."


# ---------------------------------------------------------------- 문장 분리

def test_basic_split():
    assert sentences("We test it. Results improve. Done!") == ["We test it.", "Results improve.", "Done!"]


def test_abbreviations_do_not_split():
    text = ("We use BERT, i.e. a transformer. Results improve vs. the baseline (cf. Table 2). "
            "The value is ca. 3.5 in Eq. 4. As noted in Ref. 12, it holds. Smith et al. (2020) agree. "
            "The U.S. data differ.")
    assert len(sentences(text)) == 6


def test_numbers_and_versions():
    assert sentences("The effect was significant (p < 0.05). We then tested it.") == [
        "The effect was significant (p < 0.05).", "We then tested it."]
    assert sentences("We use version v1.0. It is stable.") == ["We use version v1.0.", "It is stable."]
    assert sentences("Accuracy rose to 91.2%. However, recall fell.") == ["Accuracy rose to 91.2%.", "However, recall fell."]


def test_math_is_not_split():
    assert len(sentences(r"We set \( x = 1. Y = 2 \) here. Then we train.")) == 2
    assert len(sentences("We set $x = 1. Y$ here. Then we train.")) == 2


def test_citation_with_period_is_not_split():
    assert len(sentences("This holds (Smith et al., 2020). Next sentence.")) == 2
    assert len(sentences("See (Lee et al. 2019) for details. Next.")) == 2


def test_url_is_not_split():
    assert len(sentences("Code is at https://example.org/A.B today. Next.")) == 2


def test_spans_point_into_cleaned_text():
    t = clean("One two. Three four.").text
    assert [t[s:e] for s, e in split_sentences(t)] == ["One two.", "Three four."]
