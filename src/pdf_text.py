"""논문 PDF → 읽는 순서대로 된 텍스트 줄.

- 글자와 위치는 pdfplumber(pdfminer.six 기반)로 읽는다. AI·OCR은 쓰지 않는다(스캔 PDF는 글자가 없어 처리 불가).
- 2단 편집: 줄마다 쪽 가운데에 단 사이 빈틈(gutter)이 있는지 보고, 빈틈이 있는 줄이 이어지는 구간은
  왼쪽 단 → 오른쪽 단 순서로 읽는다. 제목·초록처럼 쪽 전체 폭을 쓰는 줄은 그 자리에서 그대로 읽는다.
- 줄 사이 간격이 평소보다 크면 빈 줄(문단 경계)을 넣는다. 절 나누기(src/sections.py)는 이 줄들을 정규식으로 본다.
"""

import io
import re
from dataclasses import dataclass, field
from statistics import median

GUTTER_MIN = 8.0          # 단 사이 빈틈으로 볼 최소 너비(pt). 낱말 사이 띄어쓰기는 보통 2~4pt
LINE_TOL = 2.5            # 같은 줄로 볼 글자 윗선 차이(pt)
PARA_GAP_RATIO = 1.45     # 줄 간격이 보통의 이 배 이상이면 문단 경계
MAX_PAGES = 40            # 너무 긴 PDF(학위논문·책)는 앞쪽만 읽는다


@dataclass
class PdfText:
    lines: list[str]
    pages: int
    read_pages: int
    title: str = ""
    two_column_pages: int = 0
    notes: list[str] = field(default_factory=list)


class PdfError(Exception):
    pass


def _group_lines(words: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= LINE_TOL:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def _split_at_gutter(row: list[dict], mid: float) -> tuple[list[dict], list[dict]] | None:
    """이 줄이 가운데 빈틈으로 나뉘면 (왼쪽 낱말, 오른쪽 낱말), 쪽 전체 폭을 쓰는 줄이면 None."""
    left = [w for w in row if w["x1"] <= mid + 1]
    right = [w for w in row if w["x0"] >= mid - 1]
    if len(left) + len(right) != len(row):
        return None                       # 가운데를 가로지르는 낱말이 있음
    if left and right and right[0]["x0"] - left[-1]["x1"] < GUTTER_MIN:
        return None                       # 가운데에 빈틈이 없음(한 단 문장)
    return left, right


def _text(ws: list[dict]) -> str:
    return " ".join(w["text"] for w in ws)


def _page_lines(page) -> tuple[list[tuple[float, float, str]], bool]:
    """한 쪽의 (윗선, 글자 크기, 줄 글자) 목록을 읽는 순서로. 두 번째 값은 2단 구간이 있었는지."""
    # x_tolerance를 기본(3)보다 줄여야 양쪽 맞춤으로 좁아진 띄어쓰기도 낱말 경계로 본다.
    # 세로로 찍힌 글자(arXiv 옆면 도장 등)는 본문이 아니라서 뺀다.
    words = [w for w in page.extract_words(x_tolerance=1.2, keep_blank_chars=False, use_text_flow=False,
                                           extra_attrs=["size", "upright"]) if w["upright"]]
    if not words:
        return [], False
    mid = float(page.width) / 2
    rows = _group_lines(words)
    out: list[tuple[float, float, str]] = []
    block_l: list[tuple[float, float, str]] = []
    block_r: list[tuple[float, float, str]] = []
    split_rows = 0

    def flush():
        out.extend(block_l)
        out.extend(block_r)
        block_l.clear()
        block_r.clear()

    for row in rows:
        size = median(w["size"] for w in row)
        parts = _split_at_gutter(row, mid)
        if parts is None:
            flush()
            out.append((row[0]["top"], size, _text(row)))
            continue
        left, right = parts
        if left and right:
            split_rows += 1
        if left:
            block_l.append((left[0]["top"], median(w["size"] for w in left), _text(left)))
        if right:
            block_r.append((right[0]["top"], median(w["size"] for w in right), _text(right)))
    flush()
    return out, split_rows >= 5


def _with_paragraphs(lines: list[tuple[float, float, str]]) -> list[str]:
    """줄 간격이 크거나(문단·제목 앞뒤) 단이 바뀌어 위로 돌아가면 빈 줄을 넣는다."""
    gaps = [b[0] - a[0] for a, b in zip(lines, lines[1:]) if 0 < b[0] - a[0] < 40]
    usual = median(gaps) if gaps else 12.0
    out: list[str] = []
    for i, (top, size, text) in enumerate(lines):
        if i:
            prev_top, prev_size, _ = lines[i - 1]
            gap = top - prev_top
            if gap < 0 or gap > usual * PARA_GAP_RATIO or abs(size - prev_size) > 0.8:
                out.append("")
        out.append(text)
    return out


def extract(data: bytes) -> PdfText:
    import pdfplumber

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:                # 깨진 파일·암호 걸린 파일
        raise PdfError("PDF를 열지 못했어요. 암호가 걸렸거나 손상된 파일일 수 있어요.") from e
    with pdf:
        total = len(pdf.pages)
        lines: list[str] = []
        two_col = 0
        title = ""
        for n, page in enumerate(pdf.pages[:MAX_PAGES]):
            rows, is_two = _page_lines(page)
            two_col += is_two
            if n == 0 and rows:
                big = max(s for _, s, _ in rows)
                title = " ".join(t for _, s, t in rows[:12] if s >= big - 0.5)
            lines += _with_paragraphs(rows)
            lines.append("")              # 쪽 경계
            page.flush_cache()
        meta_title = (pdf.metadata or {}).get("Title") or ""
    if not any(ln.strip() for ln in lines):
        raise PdfError("PDF에서 글자를 찾지 못했어요. 스캔한 이미지 PDF는 지원하지 않아요(글자를 선택할 수 있는 PDF만 가능).")
    notes = []
    if total > MAX_PAGES:
        notes.append(f"{total}쪽 중 앞 {MAX_PAGES}쪽만 읽었어요.")
    if isinstance(meta_title, str) and len(meta_title.split()) >= 3 and not re.search(r"\.(?:dvi|tex|pdf)$", meta_title):
        title = meta_title.strip()
    return PdfText(lines=lines, pages=total, read_pages=min(total, MAX_PAGES), title=title.strip(),
                   two_column_pages=two_col, notes=notes)
