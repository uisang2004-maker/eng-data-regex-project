"""PDF 글자 읽기(2단 순서)·절 나누기·긴 글 묶음 번역 테스트. 시험용 PDF는 코드로 직접 만든다(외부 파일 없음)."""

import re

import pytest

from src import patterns as P
from src import translate as T
from src import usage
from src.pdf_text import PdfError, extract
from src.sections import heading, split_paper


def make_pdf(pages: list[list[tuple[float, float, str]]], size: float = 10) -> bytes:
    """(x, y, 글자) 목록으로 된 쪽들을 Helvetica로 찍은 최소 PDF(A4 폭 612pt)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for items in pages:
        body = "".join(f"BT /F1 {size} Tf {x} {y} Td ({t.replace('(', '[').replace(')', ']')}) Tj ET\n"
                       for x, y, t in items)
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}endstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out.encode("latin-1")))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


def two_column_page() -> list[tuple[float, float, str]]:
    items = [(200, 760, "A Tiny Two Column Paper")]          # 쪽 전체 폭 제목(가운데)
    left = ["Abstract", "", "We propose a small method.", "It reads the left column first.",
            "One more left line.", "Left side ends here."]
    right = ["1 Introduction", "", "The right column comes second.", "It continues the paper text.",
             "One more right line.", "Right side ends here."]
    for k, (l, r) in enumerate(zip(left, right)):
        y = 700 - k * 14
        if l:
            items.append((60, y, l))
        if r:
            items.append((330, y, r))
    return items


def test_two_column_reading_order():
    pdf = extract(make_pdf([two_column_page()]))
    text = "\n".join(pdf.lines)
    assert text.index("left column first") < text.index("Left side ends") < text.index("1 Introduction")
    assert text.index("1 Introduction") < text.index("right column comes second")
    assert pdf.two_column_pages == 1


def test_split_two_column_pdf_into_sections():
    pdf = extract(make_pdf([two_column_page()]))
    paper = split_paper(pdf.lines, pdf.title)
    assert [s.title for s in paper.sections] == ["Abstract", "1 Introduction"]
    assert paper.sections[0].text.startswith("We propose a small method.")
    assert "Tiny Two Column" not in paper.chars.__str__() + paper.sections[0].text   # 앞머리(제목·저자)는 버림


def test_empty_pdf_is_error():
    with pytest.raises(PdfError):
        extract(make_pdf([[]]))
    with pytest.raises(PdfError):
        extract(b"not a pdf")


@pytest.mark.parametrize("line,last,want", [
    ("1 Introduction", 0, ("top", "1 Introduction")),
    ("1. Introduction", 0, ("top", "1 Introduction")),
    ("II. RELATED WORK", 1, ("top", "II Related Work")),
    ("1 I NTRODUCTION", 0, ("top", "1 Introduction")),                # 작은 대문자 글꼴 조각
    ("R EFERENCES", 4, ("end", "REFERENCES")),
    ("5 RNNenc-50", 4, None),                                       # 표 안 모델 이름
    ("3.2 Pre-training BERT", 3, ("sub", "3.2 Pre-training BERT")),
    ("ABSTRACT", 0, ("top", "Abstract")),
    ("References", 5, ("end", "References")),
    ("5 Experiments", 2, None),                                   # 차례가 안 맞음(3이어야 함)
    ("4 We note that in the literature the bidirectional Trans-", 3, None),   # 번호 각주
    ("2 Results of 12 runs 34 45", 1, None),                      # 숫자가 많은 표 줄
    ("1 We propose a method.", 0, None),                          # 마침표로 끝나는 문장
])
def test_heading_rules(line, last, want):
    assert heading(line, last) == want


def test_noise_and_rejoin():
    lines = ["Abstract", "", "We study broken lines that con-", "", "tinue after a column break.", "",
             "Figure 1: A caption that should go.", "", "∗ Equal contribution.", "", "3 Footnote text here.", "",
             "0.1 0.2 0.3 0.4 0.5", "", "Real text ends.", "", "References", "", "[1] A. Author. Title. 2020."]
    paper = split_paper(lines)
    t = paper.sections[0].text
    assert "continue after a column break." in t
    assert "caption" not in t and "Equal" not in t and "Footnote" not in t and "0.3" not in t
    assert "Author" not in t and paper.sections[0].dropped == 4


def test_no_headings_falls_back_to_one_block():
    paper = split_paper(["Just some text without headings.", "More text."])
    assert [s.title for s in paper.sections] == ["본문"] and paper.notes


# ---------------------------------------------------------------- 긴 글 묶음 번역

def test_chunk_ranges_respect_limit():
    sents = ["a" * 40] * 10
    ranges = T.chunk_ranges(sents, 100)
    assert ranges[0] == (0, 2) and ranges[-1][1] == 10
    assert all(sum(len(s) + 1 for s in sents[a:b]) <= 100 for a, b in ranges)
    assert T.chunk_ranges(["x" * 500], 100) == [(0, 1)]           # 한 문장이 더 길어도 그 문장만 한 묶음


def test_translate_chunked_merges_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "CACHE_PATH", tmp_path / "c.json")
    calls = []

    def fake(texts, key, split):
        calls.append(texts)
        return [re.sub(r"<s>", "<s>KO:", t) for t in texts]

    sents = [f"Sentence number {i} is here." for i in range(9)]
    r = T.translate_chunked(sents, 60, api_key="k", caller=fake, use_file_cache=False)
    assert r.ko == [f"KO:{s}" for s in sents] and r.mode == "aligned"
    assert len(calls) == len(T.chunk_ranges(sents, 60)) > 1
    assert len(r.ko_marks) == len(sents) and len(r.protected) == len(sents)


def test_translate_chunked_reports_error():
    def boom(texts, key, split):
        raise T.TranslationError("막힘")

    r = T.translate_chunked(["One sentence."] * 5, 20, api_key="k", caller=boom, use_file_cache=False)
    assert r.ko is None and r.error == "막힘"


def test_engine_limits(tmp_path):
    path = tmp_path / "u.json"
    assert usage.check(3500, 0, path) is not None                         # DeepL: 한 번 3,000자
    assert usage.check(3500, 0, path, engine="claude") is None            # Claude: 4,000자
    assert usage.check(100, 59, path, engine="claude") is None
    assert "번까지" in usage.check(100, 60, path, engine="claude")


# ---------------------------------------------------------------- 앞머리·저자 정보 거르기, 쪽 묶기

from src.pdf_text import SMALL_MARK
from src.sections import Paper, Section, nice_title, paper_pages


def test_ieee_inline_abstract_and_author_footnotes_removed():
    lines = ["Fast Thing: A Title", "Alice Kim, Bob Lee", "",
             "Abstract—We propose a fast detector. It works well.", "",
             "Index Terms—Object Detection, Region Proposal.", "",
             "1 INTRODUCTION", "", "Detection is an important task in vision research.", "",
             "• A. Kim is with University of Somewhere, Seoul.", "E-mail: alice@uni.ac.kr", "",
             "We contact {alice,bob}@lab.org for code and data. " + "This long paragraph keeps going. " * 30, "",
             "R EFERENCES", "", "[1] Someone. A paper. 2020."]
    paper = split_paper(lines)
    assert [s.title for s in paper.sections] == ["Abstract", "1 Introduction"]
    assert paper.sections[0].text == "We propose a fast detector. It works well."
    body = paper.sections[1].text
    assert "University" not in body and "alice@" not in body and "@lab.org" not in body and "Index Terms" not in body
    assert "We contact for code and data" in body                 # 긴 문단은 남기고 이메일만 지움
    assert "Someone" not in body


def test_small_font_paragraphs_dropped_except_all_small_abstract():
    lines = ["ABSTRACT", "", SMALL_MARK + "Our abstract is printed in a small font.", "",
             "1 Introduction", "", "Body text in the normal font continues here.", "",
             SMALL_MARK + "∗Equal contribution. Work done while at a lab.", "",
             SMALL_MARK + "3 We note a footnote that looks like a heading", "", "More body text follows here."]
    paper = split_paper(lines)
    assert paper.sections[0].text == "Our abstract is printed in a small font."
    t = paper.sections[1].text
    assert "Equal" not in t and "footnote" not in t and "More body text" in t
    assert [s.title for s in paper.sections] == ["Abstract", "1 Introduction"]


def test_nice_title_keeps_acronyms_from_body():
    keep = frozenset({"BERT", "R-CNN"})
    assert nice_title("BERT", keep) == "BERT"
    assert nice_title("RELATED WORK", keep) == "Related Work"
    assert nice_title("LEARNING TO ALIGN AND TRANSLATE", keep) == "Learning to Align and Translate"
    assert nice_title("FASTER R-CNN", keep) == "Faster R-CNN"
    assert nice_title("Mixed Case Title", keep) == "Mixed Case Title"


def test_paper_pages_groups_sections():
    secs = [Section(t, text="x.") for t in ["Abstract", "1 Introduction", "2 Method", "5 Discussion",
                                           "6 Conclusion", "Acknowledgments"]]
    pages = paper_pages(Paper("t", secs))
    assert pages == {"초록": [0], "본문": [1, 2], "결론": [3, 4]}
    assert "결론" not in paper_pages(Paper("t", secs[:3]))


def test_plain_len_ignores_tags_so_chunks_fit_limit():
    xml = '<s>We <m c="hedge" i="0">may</m> win &amp; lose.</s>'
    assert T.plain_len(xml) == len("We may win & lose.")
    sents = [f"Sentence {i} has some words in it." for i in range(200)]
    for a, b in T.chunk_ranges(sents, 4000):
        assert T.plain_len(" ".join(f"<s>{s}</s>" for s in sents[a:b])) <= 4000


# ---------------------------------------------------------------- 표 찾기

from src import tables as TB


def make_pdf_with_rules(items, rules, size=10):
    """make_pdf에 가로선(re 연산자로 그린 얇은 사각형)을 더한 PDF."""
    body = "".join(f"BT /F1 {size} Tf {x} {y} Td ({t}) Tj ET\n" for x, y, t in items)
    body += "".join(f"{x0} {y} {x1 - x0} 0.5 re f\n" for x0, x1, y in rules)
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            f"<< /Length {len(body)} >>\nstream\n{body}endstream",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 3 0 R >> >> >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out.encode("latin-1")))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


def test_find_table_by_caption_and_rules():
    items = [(72, 700, "Table 1: Accuracy of two models on a test set."),
             (80, 670, "Model"), (300, 670, "Accuracy"),
             (80, 650, "Base"), (300, 650, "71.2"),
             (80, 635, "Ours"), (300, 635, "74.9"),
             (72, 560, "Table 2. A table without any rules."),
             (72, 400, "Body text says Table 1 shows our gains over the base model in this short paper.")]
    rules = [(72, 400, 684), (72, 400, 662), (72, 400, 628)]
    ts = TB.find_tables(make_pdf_with_rules(items, rules))
    assert [t.num for t in ts] == [1, 2]
    assert ts[0].caption.startswith("Table 1: Accuracy") and not ts[0].whole_page and ts[0].png[:4] == b"\x89PNG"
    assert ts[1].whole_page                       # 선이 없으면 쪽 전체 이미지로


def test_table_mentions():
    assert TB.mentioned("As Table 3 shows, and Tables 2 and 4, see Tab. 5; also Table 3 again.") == [3, 2, 4, 5]
    assert TB.mentioned("A stable table-like result.") == []
