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
    ("II. RELATED WORK", 1, ("top", "II RELATED WORK")),
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
