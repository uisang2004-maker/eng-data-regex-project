"""논문 PDF → 읽는 순서대로 된 텍스트 줄.

- 글자와 위치는 pdfplumber(pdfminer.six 기반)로 읽는다. AI·OCR은 쓰지 않는다(스캔 PDF는 글자가 없어 처리 불가).
- 2단 편집: 줄마다 쪽 가운데에 단 사이 빈틈(gutter)이 있는지 보고, 빈틈이 있는 줄이 이어지는 구간은
  왼쪽 단 → 오른쪽 단 순서로 읽는다. 제목·초록처럼 쪽 전체 폭을 쓰는 줄은 그 자리에서 그대로 읽는다.
- 줄은 글자 아랫선(baseline)으로 묶고, 붙어 있는 낱말 조각(작은 대문자 글꼴의 `I` + `NTRODUCTION`)은 띄우지 않고 잇는다.
- 줄 사이 간격이 평소보다 크면 빈 줄(문단 경계)을 넣는다. 절 나누기(src/sections.py)는 이 줄들을 정규식으로 본다.
- 줄 전체가 본문과 다른 굵은 글꼴이면 제목 후보 표시를 붙인다(본문보다 크면 HEAD_MARK, 같으면 SUB_MARK).
  번호 없는 제목(백과사전·인문학 글)을 찾기 위한 단서일 뿐이고, 제목으로 받을지는 sections.py의 정규식이 정한다.
"""

import io
import re
from dataclasses import dataclass, field
from statistics import median

GUTTER_MIN = 8.0          # 단 사이 빈틈으로 볼 최소 너비(pt). 낱말 사이 띄어쓰기는 보통 2~4pt
LINE_TOL = 2.5            # 같은 줄로 볼 글자 아랫선 차이(pt). 윗선은 작은 대문자 글꼴에서 글자마다 달라 쓰지 않는다
JOIN_GAP = 0.8            # 낱말 사이가 이보다 좁으면(글꼴만 바뀐 조각) 띄어 쓰지 않고 잇는다
PARA_GAP_RATIO = 1.45     # 줄 간격이 보통의 이 배 이상이면 문단 경계
MAX_PAGES = 40            # 너무 긴 PDF(학위논문·책)는 앞쪽만 읽는다
SMALL_GAP = 0.9           # 본문 글자보다 이만큼(pt) 이상 작은 줄은 각주·캡션·표 글자로 보고 표시해 둔다
SMALL_MARK = "\x1f"       # 작은 글자 줄 앞에 붙이는 표시(src/sections.py가 보고 뗀다)
HEAD_MARK = "\x1e"        # 본문보다 큰 굵은 글꼴 줄(절 제목 후보)
SUB_MARK = "\x1d"         # 본문 크기의 굵은 글꼴 줄(소제목 후보)
MARKS = SMALL_MARK + HEAD_MARK + SUB_MARK
HEAD_GAP = 0.5            # 본문보다 이만큼(pt) 이상 크면 절 제목 후보, 아니면 소제목 후보
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi|medi(?:um)?\b|[-_,](?:b|bd|bx|hev)\b|cmbx", re.I)
ITALIC_FONT = re.compile(r"ital|obli|[-_](?:i|it|bi|lightit)\b", re.I)


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
    for w in sorted(words, key=lambda w: (round(w["bottom"]), w["x0"])):
        if rows and abs(rows[-1][0]["bottom"] - w["bottom"]) <= LINE_TOL:
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
    out = ""
    for i, w in enumerate(ws):
        if i and w["x0"] - ws[i - 1]["x1"] > JOIN_GAP:
            out += " "
        out += w["text"]
    return out


def _font(w: dict) -> str:
    """낱말의 글꼴(글자들이 한 글꼴일 때). 'ABCDEF+Helvetica-Bold' → 'Helvetica-Bold'. 낱말 나누기는 글꼴과 상관없이 그대로 둔다."""
    fonts = {c.get("fontname", "").split("+")[-1] for c in w.get("chars", ())}
    return fonts.pop() if len(fonts) == 1 else "?"


def _line(ws: list[dict]) -> tuple[float, float, str, float, str]:
    """(아랫선, 글자 크기 중앙값, 줄 글자, 가장 큰 글자 크기, 줄 전체가 한 글꼴이면 그 이름 아니면 "")."""
    fonts = {_font(w) for w in ws}
    return (ws[0]["bottom"], median(w["size"] for w in ws), _text(ws), max(w["size"] for w in ws),
            fonts.pop() if len(fonts) == 1 and "?" not in fonts else "")


def _page_lines(page) -> tuple[list[tuple[float, float, str, float]], bool]:
    """한 쪽의 줄 목록(_line)을 읽는 순서로. 두 번째 값은 2단 구간이 있었는지."""
    # x_tolerance를 기본(3)보다 줄여야 양쪽 맞춤으로 좁아진 띄어쓰기도 낱말 경계로 본다.
    # 세로로 찍힌 글자(arXiv 옆면 도장 등)는 본문이 아니라서 뺀다.
    words = [w for w in page.extract_words(x_tolerance=1.2, keep_blank_chars=False, use_text_flow=False,
                                           extra_attrs=["size", "upright"], return_chars=True) if w["upright"]]
    if not words:
        return [], False
    mid = float(page.width) / 2
    rows = _group_lines(words)
    out: list[tuple[float, float, str, float]] = []
    block_l: list[tuple[float, float, str, float]] = []
    block_r: list[tuple[float, float, str, float]] = []
    split_rows = 0

    def flush():
        out.extend(block_l)
        out.extend(block_r)
        block_l.clear()
        block_r.clear()

    for row in rows:
        parts = _split_at_gutter(row, mid)
        if parts is None:
            flush()
            out.append(_line(row))
            continue
        left, right = parts
        if left and right:
            split_rows += 1
        if left:
            block_l.append(_line(left))
        if right:
            block_r.append(_line(right))
    flush()
    return out, split_rows >= 5


def _body_size(pages: list[list[tuple[float, float, str, float]]]) -> float:
    """본문 글자 크기: 글자 수로 가중한 크기 중앙값."""
    sizes = sorted((round(r[1], 1), len(r[2])) for rows in pages for r in rows)
    total, acc = sum(n for _, n in sizes), 0
    for size, n in sizes:
        acc += n
        if acc * 2 >= total:
            return size
    return 10.0


def _body_font(pages) -> str:
    """본문 글꼴: 글자 수가 가장 많은 글꼴(한 글꼴로만 된 줄 기준)."""
    count: dict[str, int] = {}
    for rows in pages:
        for r in rows:
            if r[4]:
                count[r[4]] = count.get(r[4], 0) + len(r[2])
    return max(count, key=count.get) if count else ""


def _head_mark(row, body: float, body_font: str) -> str:
    """줄 전체가 본문과 다른 굵은(기울지 않은) 글꼴이고 짧으면 제목 후보 표시."""
    font = row[4]
    if (not font or font == body_font or not BOLD_FONT.search(font) or ITALIC_FONT.search(font)
            or len(row[2].split()) > 12 or row[1] < body - 0.2):
        return ""
    return HEAD_MARK if row[1] >= body + HEAD_GAP else SUB_MARK


def _with_paragraphs(lines: list[tuple], body: float = 0.0, body_font: str = "") -> list[str]:
    """줄 간격이 크거나(문단·제목 앞뒤) 단이 바뀌어 위로 돌아가면 빈 줄을 넣는다."""
    gaps = [b[0] - a[0] for a, b in zip(lines, lines[1:]) if 0 < b[0] - a[0] < 40]
    usual = median(gaps) if gaps else 12.0
    out: list[str] = []
    for i, row in enumerate(lines):
        top, size, text = row[:3]
        if i:
            prev_top, prev_size = lines[i - 1][:2]
            gap = top - prev_top
            if gap < 0 or gap > usual * PARA_GAP_RATIO or abs(size - prev_size) > 0.8:
                out.append("")
        small = body and size < body - SMALL_GAP
        out.append((SMALL_MARK if small else _head_mark(row, body, body_font) if body else "") + text)
    return out


def _first_page_title(pages) -> str:
    """첫 쪽 위쪽에서 가장 큰 글자 줄. 여러 쪽에 똑같이 찍힌 줄(출판사 표시 'Author's personal copy' 같은
    워터마크·머리글)은 제목이 아니므로 뺀다."""
    if not pages or not pages[0]:
        return ""
    seen: dict[str, int] = {}
    for rows in pages:
        for t in {r[2] for r in rows[:12]}:
            seen[t] = seen.get(t, 0) + 1
    rep = len(pages) >= 2
    rows = [r for r in pages[0][:12] if not (rep and seen[r[2]] >= 2 and seen[r[2]] * 2 >= len(pages))]
    if not rows:
        return ""
    big = max(r[3] for r in rows)
    return " ".join(r[2] for r in rows if r[3] >= big - 0.5)


def extract(data: bytes) -> PdfText:
    import pdfplumber

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:                # 깨진 파일·암호 걸린 파일
        raise PdfError("PDF를 열지 못했어요. 암호가 걸렸거나 손상된 파일일 수 있어요.") from e
    with pdf:
        total = len(pdf.pages)
        pages: list[list[tuple]] = []
        two_col = 0
        for page in pdf.pages[:MAX_PAGES]:
            rows, is_two = _page_lines(page)
            two_col += is_two
            pages.append(rows)
            page.flush_cache()
        title = _first_page_title(pages)
        body = _body_size(pages)
        body_font = _body_font(pages)
        lines: list[str] = []
        for rows in pages:
            lines += _with_paragraphs(rows, body, body_font)
            lines.append("")              # 쪽 경계
        meta_title = (pdf.metadata or {}).get("Title") or ""
    if not any(ln.strip(MARKS + " ") for ln in lines):
        raise PdfError("PDF에서 글자를 찾지 못했어요. 스캔한 이미지 PDF는 지원하지 않아요(글자를 선택할 수 있는 PDF만 가능).")
    notes = []
    if total > MAX_PAGES:
        notes.append(f"{total}쪽 중 앞 {MAX_PAGES}쪽만 읽었어요.")
    if isinstance(meta_title, str) and len(meta_title.split()) >= 3 and not re.search(r"\.(?:dvi|tex|pdf)$", meta_title):
        title = meta_title.strip()
    return PdfText(lines=lines, pages=total, read_pages=min(total, MAX_PAGES), title=title.strip(),
                   two_column_pages=two_col, notes=notes)
