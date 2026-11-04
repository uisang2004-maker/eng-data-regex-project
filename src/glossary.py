"""단어표: 이 글을 읽는 데 필요한 **어려운 단어(전문용어)**를 한 표로 모은다.

기준: **한국어로 옮겨도 뜻이 바로 안 풀릴 전문용어**만 넣는다(이의상 요청, 2026-11-04).
- 기준 자료: wordfreq 3.1.1의 영어 단어 빈도(Zipf 척도). data/processed/en_word_zipf.tsv에 Zipf 3.0 이상인
  단어만 저장해 두었다(CC BY-SA 4.0, 출처는 파일 머리말과 README).
- 낱말은 Zipf 3.0 미만(목록에 없으면 0)일 때만, 3번 이상 나오는 반복 용어는 3.5 미만(transformer 3.37)일 때 넣는다.
- 흔한 말에 접두·접미사가 붙은 말(unlabeled ← label, bidirectional ← direction, outperforming ← perform)은
  한국어로 옮기면 풀리므로 뺀다. 부사(-ly), 인용 속 저자 이름(Vaswani et al.), 수식 기호가 붙은 말(dmodel), AI 같은 약어도 뺀다.
  (샘플 300편: 초록당 평균 10.5개 → 4.6개, BERT Introduction 33개 → 8개)
- 두 단어 용어는 하나라도 전문용어 낱말이 있으면 넣는다. 약어와 모델·데이터셋 이름(대문자가 섞인 말)은 넣는다.

정규식이 찾은 결과만 모은다(새로 지어내지 않음). 한국어는 번역을 실행했을 때 번역기가 옮긴 태그에서 가져온다.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from src import patterns as P
from src.extract import Analysis, frequent_terms

ROOT = Path(__file__).resolve().parents[1]
ZIPF_PATH = ROOT / "data" / "processed" / "en_word_zipf.tsv"

EASY_ZIPF = 3.5     # (예전 기준) 이 이상이면 일상어
HARD_ZIPF = 3.0     # 이 미만(또는 목록에 없음)이면 난이도 '상'
JARGON_ZIPF = 3.0           # 낱말 하나가 전문용어가 되려면 이보다 드물어야 한다
TERM_JARGON_ZIPF = 3.5      # 3번 이상 나오는 반복 용어는 조금 넓게(transformer 3.37, embedding 3.0)
COMMON_STEM_ZIPF = 4.0      # 접두·접미사를 떼어 이만큼 흔한 낱말이 나오면 한국어로 풀리는 말
KNOWN_ACRONYM_ZIPF = 4.0    # AI(4.23)처럼 일상에서도 쓰는 약어는 뺀다

KO_GLOSS_PARTICLE = re.compile(r"(?<=[가-힣])(?:을|를|에서|에|으로|은|는)$")
"""단어표의 한국어 대응어 끝 조사를 뗀다('관련성을' → '관련성'). 명사 끝 글자와 헷갈리는 가·이·의·로는 일부러 뺐다."""

KIND_LABEL = {"abbr": "약어", "name": "고유 이름", "term": "반복 용어", "explained": "설명된 용어", "rare": "어려운 단어"}
TIP_TERM = re.compile(r"'(?P<term>[^']+)'의")
WORD = re.compile(r"\b[A-Za-z][A-Za-z]+(?:-[A-Za-z]+)*\b")
NAME = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][A-Za-z]*)+\b|\b[A-Z][A-Za-z]*\d[A-Za-z\d-]*\b")
"""대문자가 중간에 있거나 숫자가 섞인 이름: HiLabel, AccentNet, GPT4o."""


@dataclass
class Entry:
    term: str
    kinds: list[str] = field(default_factory=list)
    level: str = ""                        # 상 / 중 / 약어·이름은 빈칸
    zipf: float | None = None
    count: int = 0
    first_sentence: int | None = None      # 1부터
    explanation: str = ""                  # 원문에서 가져온 풀네임·설명
    korean: str = ""                       # 번역문에서 가져온 대응어(번역을 실행했을 때만)
    ai_meaning: str = ""                   # AI 풀이(참고용, 'AI로 뜻 풀이 받기'를 눌렀을 때만, src/explain.py)


@lru_cache(maxsize=1)
def _zipf_table() -> dict[str, float]:
    table = {}
    with ZIPF_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or "\t" not in line:
                continue
            w, z = line.rstrip("\n").split("\t")
            table[w] = float(z)
    return table


def _forms(w: str) -> list[str]:
    """빈도표에서 찾을 기본형 후보(복수·과거·-ing)."""
    w = w.lower()
    out = [w]
    if w.endswith("ies"):
        out.append(w[:-3] + "y")
    if w.endswith("es"):
        out.append(w[:-2])
    if w.endswith("s"):
        out.append(w[:-1])
    if w.endswith("ed"):
        out += [w[:-2], w[:-1]]
    if w.endswith("ing"):
        out += [w[:-3], w[:-3] + "e"]
    return out


def word_zipf(word: str) -> float:
    """일상 영어 빈도(Zipf). 목록에 없으면 0. 하이픈 단어는 통째로 없으면 가장 드문 조각 기준."""
    table = _zipf_table()
    best = max((table.get(f, 0.0) for f in _forms(word)), default=0.0)
    if best == 0.0 and "-" in word:
        parts = [p for p in word.split("-") if p]
        return min((word_zipf(p) for p in parts), default=0.0)
    return best


def term_zipf(term: str) -> float:
    """두 단어 이상이면 더 드문 단어 기준."""
    return min((word_zipf(w) for w in term.split()), default=0.0)


def level_of(z: float) -> str:
    return "상" if z < HARD_ZIPF else "중"


def is_hard(term: str) -> bool:
    return term_zipf(term) < EASY_ZIPF


def _stems(w: str) -> set[str]:
    """접두사 하나·접미사 두 번까지 떼어 본 후보: unidirectionality → directionality, directional, direction …"""
    w = w.lower()
    cands = {w}
    m = P.JARGON_PREFIX.match(w)
    if m:
        cands.add(w[m.end():])
    for _ in range(2):
        cands |= {P.JARGON_SUFFIX.sub("", c) for c in cands}
    cands |= {c[:-1] for c in cands if len(c) >= 4 and c[-1] == c[-2]}    # summing → summ → sum
    return {c for c in cands if len(c) >= 3 and c != w}


def derived_from_common(w: str) -> bool:
    """흔한 낱말에 접두·접미사가 붙은 것(unlabeled ← label, bidirectional ← direction, outperforming ← perform).
    한국어로 옮기면 바로 풀리는 말이라 전문용어로 보지 않는다."""
    return any(word_zipf(c) >= COMMON_STEM_ZIPF for c in _stems(w))


def is_jargon_word(w: str, limit: float = JARGON_ZIPF) -> bool:
    low = w.lower()
    if len(low) < 4 or not low.isalpha() or low.endswith("ly"):
        return False                       # 짧은 말, 숫자 섞인 말, 부사(holistically)는 뺀다
    if any(word_zipf(c) >= COMMON_STEM_ZIPF for c in (low[1:], low[:-1])):
        return False                       # 수식 기호가 붙은 흔한 말: dmodel(d+model), headi(head+i)
    rarity = max(word_zipf(low), word_zipf(low + "s"))     # 기본형으로 줄어든 말(approache → approaches)
    return rarity < limit and not derived_from_common(low)


def is_jargon(term: str, limit: float = JARGON_ZIPF) -> bool:
    """한국어로 옮겨도 뜻이 바로 안 풀릴 전문용어인가: 낱말(하이픈 조각 포함) 하나라도 드물고 흔한 말에서 온 말이 아니면."""
    return any(is_jargon_word(p, limit) for p in re.split(r"[\s-]+", term))


def _masked(text: str) -> str:
    """인용·주소 안의 낱말(저자 이름 Vaswani, github)은 단어표 후보가 아니라서 같은 길이 빈칸으로 가린다."""
    for pat in (P.CITE_AUTHOR, P.CITE_NUM, P.URL, P.CITE_NARRATIVE):
        text = pat.sub(lambda m: " " * len(m.group(0)), text)
    return text


def rare_word_spans(text: str, starts: frozenset[int] = frozenset()) -> list[tuple[int, int, str]]:
    """전문용어 낱말(is_jargon_word)의 위치와 기본형. 기능어·논문 일반어·인용 속 이름은 뺀다.
    문장 첫머리가 아닌 곳의 대문자 낱말은 사람·기관 이름으로 보고 뺀다(starts: 문장 시작 위치)."""
    out = []
    for m in WORD.finditer(_masked(text)):
        w = m.group(0)
        low = w.lower()
        if len(w) < 4 or low in P.TERM_STOPWORDS or w.isupper() or any(f in P.TERM_GENERIC for f in _forms(w)):
            continue
        if w[0].isupper() and m.start() not in starts:
            continue
        if any(is_jargon_word(p) for p in low.split("-")):
            out.append((m.start(), m.end(), low))
    return out


def _count(text: str, term: str) -> tuple[int, int | None]:
    pat = re.compile(rf"\b{re.escape(term)}(?:e?s|d|ed|ing)?\b", re.I)
    hits = list(pat.finditer(text))
    return len(hits), (hits[0].start() if hits else None)


def _key(term: str) -> str:
    return " ".join(_forms(w)[-1] if w.lower().endswith(("ies", "s")) and not w.lower().endswith("ss") else w.lower()
                    for w in term.split())


def build(a: Analysis, ko_marks: list | None = None) -> list[Entry]:
    """단어표 행 목록(어려운 단어 위주). 처음 나온 순서로 정렬한다."""
    entries: dict[str, Entry] = {}

    def get(term: str) -> Entry:
        k = _key(term)
        if k not in entries:
            entries[k] = Entry(term)
        return entries[k]

    starts = frozenset(s.start for s in a.sentences)
    for abbr, long_form in a.acronyms.items():
        if word_zipf(abbr.lower()) >= KNOWN_ACRONYM_ZIPF or (len(abbr) <= 3 and abbr[-1].islower()):
            continue                       # AI처럼 누구나 아는 약어, 수식 기호(KWi, QWi)
        e = get(abbr)
        e.kinds.append("abbr")
        e.explanation = long_form or "이 글에서 정의를 찾지 못함"
    for m in NAME.finditer(a.text):
        if m.group(0) not in a.acronyms:
            e = get(m.group(0))
            if "name" not in e.kinds:
                e.kinds.append("name")
    for x, y, tip in a.explanations:
        m = TIP_TERM.search(tip)
        if not m or "예시" in tip:
            continue
        term = m.group("term")
        if re.search(r"\d|\bet al\b", term) or not (is_jargon(term) or NAME.search(term) or term in a.acronyms):
            continue                       # 'et al 2018' 같은 인용 조각, 쉬운 말은 뺀다
        e = get(term)
        if "explained" not in e.kinds:
            e.kinds.append("explained")
        if not e.explanation:
            e.explanation = a.text[x:y]
    for term, _, _ in frequent_terms(a.text):
        lower_seen = re.search(rf"(?<![A-Za-z]){re.escape(term.lower())}", _masked(a.text))
        if lower_seen and is_jargon(term, TERM_JARGON_ZIPF):   # 자주 나오는 말은 조금 넓게(transformer 3.37).
            # 소문자로 한 번도 안 나오는 말(인용 속 저자 이름 Radford)은 뺀다
            e = get(term)
            if "term" not in e.kinds:
                e.kinds.append("term")
    covered = [k for k in entries]
    long_words = {w.lower() for v in a.acronyms.values() if v for w in re.split(r"[\s-]+", v)}
    for x, y, low in rare_word_spans(a.text, starts):
        k = _key(low)
        if k in entries or any(k in c.split() for c in covered) or set(re.split(r"-", low)) & long_words:
            continue        # 이미 있는 용어의 일부이거나 약어 풀네임 안의 단어는 중복이라 뺀다
        get(a.text[x:y].lower() if not a.text[x].isupper() or x == 0 else a.text[x:y]).kinds.append("rare")

    for e in entries.values():
        e.count, pos = _count(a.text, e.term)
        if pos is not None and e.term.lower() not in a.text.lower():
            e.term = WORD.match(a.text, pos).group(0)     # 기본형(approache)이 아니라 글에 나온 모양으로 보여 준다
        if pos is not None:
            e.first_sentence = next((s.idx + 1 for s in a.sentences if s.start <= pos < s.end), None)
        if not ({"abbr", "name"} & set(e.kinds)):
            e.zipf = term_zipf(e.term)
            e.level = level_of(e.zipf)

    # 한국어 대응어: 번역문 태그의 영어 원문이 용어와 같으면 그 한국어 구간(번역되지 않은 그대로면 뺌)
    for row in ko_marks or []:
        for _a, _b, _cat, en, ko in row:
            e = entries.get(_key(en or ""))
            if e and not e.korean and ko.strip().lower() != e.term.lower():
                e.korean = KO_GLOSS_PARTICLE.sub("", ko.strip())
    return sorted(entries.values(), key=lambda e: (e.first_sentence or 999, e.term.lower()))


def jargon_marks(a: Analysis) -> list[tuple[int, int, str]]:
    """번역 때 한국어 대응어를 얻으려고 보내는 어려운 단어 태그(화면에는 그리지 않음)."""
    return [(x, y, "jargon") for x, y, _ in rare_word_spans(a.text, frozenset(s.start for s in a.sentences))]


def korean_marks(tr) -> list[list[tuple]]:
    """번역 결과(ko, ko_marks)를 단어표가 쓰는 (시작, 끝, 범주, 영어, 한국어) 목록으로 바꾼다."""
    if not tr or not tr.ko or not tr.ko_marks:
        return []
    return [[(a, b, c, en, ko[a:b]) for a, b, c, en in row] for ko, row in zip(tr.ko, tr.ko_marks)]


def ai_items(a: Analysis, rows: list[Entry]) -> list[tuple[str, str, str]]:
    """AI 풀이 요청용 (단어, 처음 나온 문장, 원문에서 찾은 풀네임·설명)."""
    out = []
    for e in rows:
        sent = a.sentences[e.first_sentence - 1].text if e.first_sentence else ""
        known = "" if e.explanation == "이 글에서 정의를 찾지 못함" else e.explanation
        out.append((e.term, sent, known))
    return out


def apply_ai(rows: list[Entry], meanings: dict[str, str]) -> list[Entry]:
    for e in rows:
        e.ai_meaning = meanings.get(e.term, "")
    return rows


def to_csv(rows: list[Entry]) -> bytes:
    """엑셀에서 한글이 깨지지 않도록 UTF-8 BOM을 붙인다."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["용어", "종류", "난이도", "등장 횟수", "처음 나온 문장", "풀네임·설명(원문)", "한국어(번역기 대응어)", "AI 풀이(참고용)"])
    for e in rows:
        w.writerow([e.term, ", ".join(KIND_LABEL[k] for k in e.kinds), e.level, e.count,
                    e.first_sentence or "", e.explanation, e.korean, e.ai_meaning])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def term_key(term: str) -> str:
    """단어표·툴팁에서 같은 용어로 볼 키(소문자, 복수형 정리): ``Rerankers`` → ``reranker``."""
    return _key(term)
