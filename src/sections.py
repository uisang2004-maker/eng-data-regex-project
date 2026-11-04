"""논문 전체 텍스트(PDF에서 읽은 줄) → 절(Abstract, 1 Introduction, …)로 나누기. 핵심은 정규식이다.

1. 줄마다 절 제목 정규식(patterns.SEC_NUM_HEAD / SEC_NAMED_HEAD)을 대 본다. 번호 절은 1, 2, 3…
   차례가 맞을 때만 제목으로 받아들여 표의 숫자 줄 같은 오탐을 막는다. 3.1 같은 소제목은 절을 나누지 않고 목록으로만 남긴다.
2. 첫 절 제목 앞(제목·저자·소속·이메일)은 버린다. 개인정보를 화면에 올리지 않기 위해서다.
3. References가 나오면 멈춘다(참고문헌·부록은 분석하지 않음).
4. 각주·그림/표 설명·이메일 줄(PDF_NOISE_PARA)과 낱말이 거의 없는 조각(표·수식)은 뺀다.
5. 단·쪽이 바뀌며 끊긴 문단은 앞 문단이 문장부호로 끝나지 않으면 다시 잇는다. 그다음 clean()으로 정리한다.
"""

import re
from dataclasses import dataclass, field

from src import patterns as P
from src.clean import clean
from src.pdf_text import SMALL_MARK

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
MAX_TITLE_WORDS = 10
SENT_END = re.compile(r"[.!?:][\"'”’)\]]*$")


@dataclass
class Section:
    title: str                                  # 화면에 보일 이름: "Abstract", "1 Introduction"
    text: str = ""
    subheads: list[str] = field(default_factory=list)
    dropped: int = 0                            # 뺀 조각(각주·캡션·표) 수
    paras: list[list[str]] = field(default_factory=list)


@dataclass
class Paper:
    title: str
    sections: list[Section]
    notes: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(len(s.text) for s in self.sections)


def _top_value(top: str) -> int:
    return int(top) if top.isdigit() else ROMAN.get(top.upper(), 0)


SMALL_WORDS = {"a", "an", "the", "of", "and", "for", "to", "in", "on", "with", "by", "at", "or", "via", "from"}


CAPS_WORD = re.compile(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*\b")


def caps_words(lines: list[str]) -> frozenset[str]:
    """본문(대문자로만 쓴 줄 제외)에서 대문자로 쓰인 낱말 = 약어·모델 이름(BERT, GLUE, R-CNN)."""
    return frozenset(w for ln in lines if not ln.isupper() for w in CAPS_WORD.findall(ln))


def nice_title(title: str, keep: frozenset[str] = frozenset()) -> str:
    """대문자로만 쓴 제목을 읽기 쉽게: ``RELATED WORK`` → ``Related Work``.
    본문에서도 대문자로 쓰인 낱말(keep: 약어·모델 이름)은 그대로 둔다: ``3 BERT``, ``FASTER R-CNN`` → ``Faster R-CNN``."""
    if not title.isupper():
        return title
    out = []
    for i, w in enumerate(title.split()):
        core = w.strip(":,.;()")
        if core in keep or not core.isalpha():
            out.append(w)
        elif i and core.lower() in SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def heading(line: str, last_top: int, keep: frozenset[str] = frozenset()) -> tuple[str, str] | None:
    """제목 줄이면 ("top"|"sub"|"end", 화면 이름), 아니면 None."""
    s = P.SMALL_CAPS_HEAD.sub(r"\1", line.strip())
    if P.SEC_END.match(s):
        return "end", s
    m = P.SEC_NAMED_HEAD.match(s)
    if m:
        return "top", nice_title(m.group("title").strip(), keep)
    m = P.SEC_NUM_HEAD.match(s)
    if not m:
        return None
    title = m.group("title").strip()
    words = title.split()
    if (len(words) > MAX_TITLE_WORDS or sum(w.isdigit() for w in words) > 1 or title.endswith("-")
            or len(P.SEC_TITLE_FUNCTION.findall(title)) >= 4 or any(ch.isdigit() for ch in words[0])):
        return None                              # 너무 길거나, 숫자 줄·표 이름(RNNenc-50)이거나, 끊긴 문장이거나, 문장처럼 보임
    value = _top_value(m.group("top"))
    name = f"{m.group('num').rstrip('.')} {nice_title(title, keep)}"
    if not m.group("sub"):
        return ("top", name) if value == last_top + 1 else None
    return ("sub", name) if value == last_top else None


def _is_noise(para: list[str], keep_small: bool = False) -> bool:
    if not keep_small and sum(ln.startswith(SMALL_MARK) for ln in para) * 2 > len(para):
        return True                              # 본문보다 작은 글자(각주·캡션·표). 초록은 작은 글자로 쓰는 형식이 있어 예외
    text = " ".join(ln.lstrip(SMALL_MARK) for ln in para)
    if P.PDF_NOISE_PARA.match(text):
        return True
    if len(text) < 800 and (P.PDF_FRONT_MATTER.search(text) or P.EMAIL.search(text)):
        return True                              # 소속·이메일·교신저자·저작권 같은 앞머리·각주 문단
    tokens = text.split()
    words = len(P.PDF_WORDLIKE.findall(text))
    if words < 4 and not SENT_END.search(text):
        return True                              # 그림 안 글자·축 이름 같은 짧은 조각
    return bool(tokens) and words / len(tokens) < 0.4      # 숫자·기호가 대부분인 표·수식


def _join(paras: list[list[str]]) -> str:
    """끊긴 문단 다시 잇기: 앞 문단이 문장부호로 끝나지 않으면 한 줄 개행으로 붙인다(하이픈 복원이 동작하도록)."""
    out = ""
    for p in paras:
        chunk = "\n".join(ln.lstrip(SMALL_MARK) for ln in p)
        if not out:
            out = chunk
        elif SENT_END.search(out.rstrip()):
            out += "\n\n" + chunk
        else:
            out += "\n" + chunk
    return out


def split_paper(lines: list[str], title: str = "") -> Paper:
    sections: list[Section] = []
    cur: Section | None = None
    para: list[str] = []
    last_top = 0
    notes: list[str] = []
    keep = caps_words([ln.lstrip(SMALL_MARK) for ln in lines])

    def end_para():
        nonlocal para
        if cur is not None and para:
            cur.paras.append(para)
        para = []

    for raw in lines:
        small = raw.startswith(SMALL_MARK)
        line = P.PDF_CID.sub("", raw.lstrip(SMALL_MARK)).strip()
        if not line:
            end_para()
            continue
        m = P.SEC_INLINE_ABSTRACT.match(line)
        if m and not sections:                   # 'Abstract—본문'처럼 같은 줄에서 시작하는 초록
            end_para()
            cur = Section("Abstract")
            sections.append(cur)
            para.append(m.group("rest"))
            continue
        h = None if small else heading(line, last_top, keep)     # 작은 글자 줄(번호 각주 등)은 제목이 될 수 없다
        if h:
            kind, name = h
            end_para()
            if kind == "end":
                break
            if kind == "sub":
                cur.subheads.append(name)
                continue
            m = P.SEC_NUM_HEAD.match(P.SMALL_CAPS_HEAD.sub(r"\1", line))
            if m:
                last_top = _top_value(m.group("top"))
            cur = Section(name)
            sections.append(cur)
            continue
        if cur is not None:
            para.append((SMALL_MARK if small else "") + line)
    end_para()

    if not sections:                             # 제목 줄을 하나도 못 찾으면 전체를 한 덩어리로
        cur = Section("본문")
        para = []
        for raw in lines:
            line = P.PDF_CID.sub("", raw.lstrip(SMALL_MARK)).strip()
            if line:
                para.append((SMALL_MARK if raw.startswith(SMALL_MARK) else "") + line)
            elif para:
                cur.paras.append(para)
                para = []
        if para:
            cur.paras.append(para)
        sections = [cur]
        notes.append("절 제목을 찾지 못해 전체를 한 덩어리로 보여 줘요(이메일·소속 문단은 뺐지만 저자 이름이 섞일 수 있어요).")

    for s in sections:
        # 초록을 통째로 작은 글자로 쓰는 형식(IEEE)만 작은 글자를 남긴다. 섞여 있으면 작은 쪽은 각주로 본다
        all_small = all(sum(ln.startswith(SMALL_MARK) for ln in p) * 2 > len(p) for p in s.paras)
        kept = [p for p in s.paras if not _is_noise(p, keep_small=s.title == "Abstract" and all_small)]
        s.dropped = len(s.paras) - len(kept)
        s.text = clean(P.EMAIL.sub("", _join(kept))).text     # 긴 문단 속 이메일도 지운다
        s.paras = []
    sections = [s for s in sections if s.text]
    return Paper(title=title, sections=sections, notes=notes)


PAGES = ("초록", "본문", "결론")


def paper_pages(paper: Paper) -> dict[str, list[int]]:
    """절을 초록·본문·결론 쪽으로 묶는다(절 제목 정규식). 감사의 글은 뺀다. 빈 쪽은 목록에서 빠진다."""
    pages: dict[str, list[int]] = {p: [] for p in PAGES}
    for i, s in enumerate(paper.sections):
        if s.title == "Abstract":
            pages["초록"].append(i)
        elif P.SEC_ACK_TITLE.match(s.title):
            continue
        elif P.SEC_CONCLUSION_TITLE.search(s.title):
            pages["결론"].append(i)
        else:
            pages["본문"].append(i)
    return {p: ids for p, ids in pages.items() if ids}
