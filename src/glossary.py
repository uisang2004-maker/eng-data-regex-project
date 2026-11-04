"""단어표: 이 글을 읽는 데 필요한 용어를 한 표로 모은다.

정규식이 이미 찾은 결과만 모은다(새로 지어내지 않음).
- 약어: 괄호 정의에서 찾은 풀네임, 정의를 못 찾은 약어
- 반복 용어: 3번 이상 나온 용어
- 설명된 용어: 'refers to', ', which …', 동격 등으로 설명된 용어와 그 설명(원문 발췌)
한국어는 번역을 실행했을 때, 번역기가 옮긴 형광펜 태그에서 대응어를 가져온다(추가 호출 없음).
"""

import csv
import io
import re
from dataclasses import dataclass, field

from src.extract import Analysis, frequent_terms

KIND_LABEL = {"abbr": "약어", "term": "반복 용어", "explained": "설명된 용어"}
TIP_TERM = re.compile(r"'(?P<term>[^']+)'의")


@dataclass
class Entry:
    term: str
    kinds: list[str] = field(default_factory=list)
    count: int = 0
    first_sentence: int | None = None      # 1부터
    explanation: str = ""                  # 원문에서 가져온 풀네임·설명
    korean: str = ""                       # 번역문에서 가져온 대응어(번역을 실행했을 때만)


def _count(text: str, term: str) -> tuple[int, int | None]:
    pat = re.compile(rf"\b{re.escape(term)}(?:e?s)?\b", re.I)
    hits = list(pat.finditer(text))
    return len(hits), (hits[0].start() if hits else None)


def build(a: Analysis, ko_marks: list | None = None) -> list[Entry]:
    """단어표 행 목록. 처음 나온 순서로 정렬한다."""
    entries: dict[str, Entry] = {}

    def get(term: str) -> Entry:
        key = term.lower()
        if key not in entries:
            entries[key] = Entry(term)
        return entries[key]

    for abbr, long_form in a.acronyms.items():
        e = get(abbr)
        e.kinds.append("abbr")
        e.explanation = long_form or "이 글에서 정의를 찾지 못함"
    for term, _, _ in frequent_terms(a.text):
        e = get(term)
        if "term" not in e.kinds:
            e.kinds.append("term")
    for x, y, tip in a.explanations:
        m = TIP_TERM.search(tip)
        if not m or "예시" in tip:
            continue
        e = get(m.group("term"))
        if "explained" not in e.kinds:
            e.kinds.append("explained")
        if not e.explanation:
            e.explanation = a.text[x:y]

    # 등장 횟수·처음 나온 문장
    for e in entries.values():
        e.count, pos = _count(a.text, e.term)
        if pos is not None:
            e.first_sentence = next((s.idx + 1 for s in a.sentences if s.start <= pos < s.end), None)

    # 한국어 대응어: 번역문 형광펜 태그의 영어 원문이 용어와 같으면 그 한국어 구간
    if ko_marks:
        for row in ko_marks:
            for ka, kb, _cat, en, *rest in [(*m,) for m in row]:
                ko = rest[0] if rest else None
                if ko is None:
                    continue
                e = entries.get((en or "").lower().rstrip("s"))
                if e is None:
                    e = entries.get((en or "").lower())
                if e and not e.korean and ko.strip().lower() != e.term.lower():   # 약어처럼 번역되지 않은 그대로면 빼기
                    e.korean = ko
    return sorted(entries.values(), key=lambda e: (e.first_sentence or 999, e.term.lower()))


def korean_marks(tr) -> list[list[tuple]]:
    """번역 결과(ko, ko_marks)를 단어표가 쓰는 (시작, 끝, 범주, 영어, 한국어) 목록으로 바꾼다."""
    if not tr or not tr.ko or not tr.ko_marks:
        return []
    return [[(a, b, c, en, ko[a:b]) for a, b, c, en in row] for ko, row in zip(tr.ko, tr.ko_marks)]


def to_csv(rows: list[Entry]) -> bytes:
    """엑셀에서 한글이 깨지지 않도록 UTF-8 BOM을 붙인다."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["용어", "종류", "등장 횟수", "처음 나온 문장", "풀네임·설명(원문)", "한국어(번역기 대응어)"])
    for e in rows:
        w.writerow([e.term, ", ".join(KIND_LABEL[k] for k in e.kinds), e.count,
                    e.first_sentence or "", e.explanation, e.korean])
    return ("﻿" + buf.getvalue()).encode("utf-8")
