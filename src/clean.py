"""입력 정리(최소 방어선)와 문장 분리."""

from collections import Counter
from dataclasses import dataclass, field

from src import patterns as P


@dataclass
class CleanResult:
    text: str
    removed_lines: list[str] = field(default_factory=list)   # 지운 쪽번호·머리말 줄 (화면의 '제거된 줄 보기')


def clean(raw: str) -> CleanResult:
    """붙여 넣은 텍스트에 최소 방어선 5종을 적용한다. 원문 단어는 바꾸지 않는다."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("’", "'").replace("‘", "'")
    removed: list[str] = []

    # 1) 숫자만 있는 줄(쪽번호), 2) 3번 이상 반복되는 짧은 줄(머리말·꼬리말)
    # 줄째 지워야 문단 중간에 빈 줄이 생기지 않는다.
    lines = text.split("\n")
    counts = Counter(s for s in (ln.strip() for ln in lines) if 0 < len(s) <= P.HEADER_MAX_LEN)
    headers = {s for s, n in counts.items() if n >= P.HEADER_MIN_REPEAT and not P.PAGE_NUMBER_LINE.fullmatch(s)}
    kept = []
    for ln in lines:
        if P.PAGE_NUMBER_LINE.fullmatch(ln) or ln.strip() in headers:
            if ln.strip() not in removed:
                removed.append(ln.strip())
            continue
        kept.append(ln)
    text = "\n".join(kept)

    # 3) 줄 끝 하이픈 복원(+ 작은 대문자 조각 붙이기) → 4) 한 줄 개행을 공백으로 → 5) 연속 공백 정리
    text = P.DEHYPHEN.sub(_dehyphen, text)
    text = P.SMALL_CAPS_SPLIT.sub(_join_small_caps, text)
    text = P.SOFT_NEWLINE.sub(" ", text)
    text = P.MULTI_SPACE.sub(" ", text)
    text = "\n\n".join(p.strip() for p in text.split("\n\n") if p.strip())
    return CleanResult(text=text.strip(), removed_lines=removed)


def _known(word: str) -> bool:
    from src.glossary import word_zipf      # glossary가 이 모듈을 간접적으로 불러서 함수 안에서 불러온다
    return word_zipf(word) > 0


LINK_WORDS = {"of", "to", "in", "on", "the", "and", "by", "for"}   # state-of-the-art, end-to-end의 가운데 낱말


def _dehyphen(m) -> str:
    a, b = m.group("a"), m.group("b")
    if a.lower() in LINK_WORDS and b in LINK_WORDS | {"art", "end"}:
        return f"{a}-{b}"                   # of-the, the-art, to-end (of+fering은 offering으로 붙인다)
    if not _known(a + b) and len(b) >= 3 and _known(b):
        return f"{a}-{b}"                   # 원래 하이픈 단어(fine-tuned, task-specific, state-of-the-art)
    return a + b


def _join_small_caps(m) -> str:
    return m.group(0) if _known(m.group("rest")) else m.group("c") + m.group("rest")


def _mask_for_split(text: str) -> str:
    """수식·인용·URL 안의 마침표에서 자르지 않도록 같은 길이의 빈칸 문자로 가린다(위치는 유지)."""
    masked = text
    for pat in (P.MATH, P.URL, P.CITE_AUTHOR, P.CITE_NUM):
        masked = pat.sub(lambda m: "\x00" * len(m.group(0)), masked)
    return masked


def split_sentences(text: str) -> list[tuple[int, int]]:
    """문장의 (시작, 끝) 위치 목록. 원문 위치를 그대로 쓰므로 하이라이트를 정확히 얹을 수 있다."""
    masked = _mask_for_split(text)
    spans, start = [], 0
    for m in P.SENT_BOUNDARY.finditer(masked):
        if P.NON_FINAL.search(masked[start:m.start()]):
            continue
        if text[start:m.start()].strip():
            spans.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans
