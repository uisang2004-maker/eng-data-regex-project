"""논문 독해 도우미 프로토타입의 정규표현식 규칙 모음.

Phase 2 검증용이다. 컨펌 후 Phase 3에서 src/patterns.py로 옮기고 테스트를 붙인다.
"""

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 전처리

# PDF 복사 시 줄 끝에서 끊긴 단어: "lan-\nguage" -> "language"
# (일부러 놓치는 경우: "state-of-\nthe-art"처럼 원래 하이픈이 있던 단어는 붙어 버린다)
DEHYPHEN = re.compile(r"(?<=[a-z])-[ \t]*\n[ \t]*(?=[a-z])")
# 문단 안의 단일 줄바꿈 -> 공백 (빈 줄은 문단 경계로 유지)
SOFT_NEWLINE = re.compile(r"(?<!\n)[ \t]*\n[ \t]*(?!\n)")
MULTI_SPACE = re.compile(r"[ \t]{2,}")
INLINE_MATH = re.compile(r"\$[^$\n]{1,120}\$")


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("’", "'").replace("‘", "'")
    text = DEHYPHEN.sub("", text)
    text = SOFT_NEWLINE.sub(" ", text)
    text = INLINE_MATH.sub("[math]", text)
    text = MULTI_SPACE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------- 문장 분리

SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\"'])|\n{2,}")
# 마침표가 있어도 문장 끝이 아닌 약어
NON_FINAL = re.compile(r"(?:\be\.g|\bi\.e|\bet al|\bvs|\bFig|\bEq|\bSec|\bcf|\bapprox|\bNo|\bal)\.$", re.I)


def split_sentences(text: str) -> list[tuple[int, int]]:
    """문장의 (시작, 끝) 위치 목록을 돌려준다."""
    spans, start = [], 0
    for m in SENT_BOUNDARY.finditer(text):
        if NON_FINAL.search(text[start:m.start()]):
            continue
        if text[start:m.start()].strip():
            spans.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


# ---------------------------------------------------------------- 약어

# 괄호 안 약어 후보: 대문자가 2개 이상 (NLP, LLMs, GPT-4, BiLSTM)
ACRONYM_DEF = re.compile(r"\(\s*(?P<abbr>(?=(?:[^A-Z)]*[A-Z]){2})[A-Za-z][A-Za-z0-9-]{1,11})\s*\)")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*")
LINKERS = {"of", "from", "and", "the", "for", "in", "on", "with", "to", "a", "an", "by", "via"}
# 정의 없이 쓰인 약어 후보
BARE_ACRONYM = re.compile(r"\b[A-Z][A-Za-z]*[A-Z][A-Za-z0-9]*s?\b")


def _letters(abbr: str) -> str:
    core = abbr[:-1] if abbr.endswith("s") and abbr[:-1].isupper() else abbr
    return "".join(ch for ch in core if ch.isupper())


def _match_long_form(abbr: str, before: str) -> str | None:
    """약어 대문자를 뒤에서부터 앞 단어(하이픈 조각 포함)의 첫 글자와 맞춘다."""
    letters = _letters(abbr).lower()
    if len(letters) < 2:
        return None
    words = WORD.findall(before)[-(len(letters) * 2 + 3):]
    i, used = len(letters) - 1, []
    for w in reversed(words):
        heads = [p[0].lower() for p in w.split("-") if p]
        # 하이픈 단어는 조각마다 약어 글자 하나씩 맡을 수 있다 (Short-Term -> ST)
        k = 0
        while k < len(heads) and i - k >= 0 and heads[-1 - k] == letters[i - k]:
            k += 1
        if k < len(heads):
            k = 1 if heads[0] == letters[i] else 0
        if k > 0:
            i -= k
            used.insert(0, w)
        elif used and w.lower() in LINKERS:
            used.insert(0, w)
        else:
            break
        if i < 0:
            break
    if i >= 0 or not used:
        return None
    while used and used[0].lower() in LINKERS:
        used.pop(0)
    return " ".join(used)


def find_acronyms(text: str) -> dict[str, str | None]:
    """{약어: 풀네임 또는 None}. 정의를 못 찾은 약어도 None으로 포함한다."""
    defs: dict[str, str | None] = {}
    for m in ACRONYM_DEF.finditer(text):
        abbr = m.group("abbr")
        key = abbr[:-1] if abbr.endswith("s") and abbr[:-1].isupper() else abbr
        long_form = _match_long_form(abbr, text[max(0, m.start() - 200):m.start()])
        if long_form and key not in defs:
            defs[key] = long_form
    for m in BARE_ACRONYM.finditer(text):
        tok = m.group(0)
        key = tok[:-1] if tok.endswith("s") and tok[:-1].isupper() else tok
        if sum(ch.isupper() for ch in key) >= 2 and key not in defs:
            defs[key] = None
    return defs


# ---------------------------------------------------------------- 단어 단위 규칙


@dataclass
class Rule:
    name: str
    category: str
    label: str
    pattern: re.Pattern
    desc: str
    examples: list[str] = field(default_factory=list)


TOKEN_RULES = [
    Rule("CITE_NUM", "ref", "인용", re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]"),
         "번호식 인용", ["[12]", "[3, 5-7]"]),
    Rule("CITE_AUTHOR", "ref", "인용",
         re.compile(r"\((?:e\.g\.,?\s*)?[A-Z][A-Za-z'-]+(?:\s+et al\.|\s+(?:and|&)\s+[A-Z][A-Za-z'-]+)?,?\s+\d{4}[a-z]?"
                    r"(?:;\s*[A-Z][A-Za-z'-]+(?:\s+et al\.|\s+(?:and|&)\s+[A-Z][A-Za-z'-]+)?,?\s+\d{4}[a-z]?)*\)"),
         "저자-연도식 인용", ["(Smith et al., 2020)", "(Lee and Kim, 2019; Park, 2021)"]),
    Rule("XREF", "ref", "참조",
         re.compile(r"\b(?:Fig(?:ure)?s?|Tables?|Eqs?|Equations?|Sec(?:tion)?s?|Appendix|Alg(?:orithm)?)\.?\s*(?:\(\d+\)|[A-Z]?\d+(?:\.\d+)*)"),
         "그림·표·수식·절 참조", ["Fig. 3", "Table 2", "Eq. (4)", "Section 5.1"]),
    Rule("HEDGE", "hedge", "추측",
         re.compile(r"\b(?:may|might|could)\b(?!\s+be\s+(?:used|applied|employed|extended|adapted|found|obtained|downloaded)\b)"
                    r"|\b(?:possibly|perhaps|potentially|presumably|likely|unlikely|suggests?|suggesting|indicates?"
                    r"|appears? to|seems? to|tend(?:s)? to|to some extent|in part)\b", re.I),
         "추측·완화 표현. 'may be used/applied'처럼 가능성만 말하는 경우는 제외",
         ["may indicate", "suggests that", "seems to"]),
    Rule("BOOSTER", "booster", "확신",
         re.compile(r"\b(?:demonstrat(?:e|es|ed|ing)|clearly|significantly|substantially|dramatically|prove[sdn]?"
                    r"|confirm(?:s|ed)?|undoubtedly|state[- ]of[- ]the[- ]art|outperform(?:s|ed|ing)?|consistently"
                    r"|remarkabl[ey]|superior)\b", re.I),
         "확신·강조 표현", ["demonstrate", "significantly", "state-of-the-art"]),
]

# ---------------------------------------------------------------- 문장 단위 규칙 (뼈대)

SKELETON_RULES = [
    Rule("SK_PROBLEM", "problem", "문제",
         re.compile(r"\b(?:however|remains? (?:an? )?(?:open|challenging|unclear|difficult|unsolved)|(?:key|major|main|central) "
                    r"(?:challenge|problem|issue|limitation|bottleneck)s?|little (?:is known|attention|work)|lack(?:s|ing)? (?:of )?"
                    r"|struggles? to|suffer(?:s)? from|is (?:costly|expensive|time-consuming)|existing (?:methods|approaches|work))\b", re.I),
         "문제 제기: 기존의 한계나 빈틈", ["However, ...", "remains challenging", "existing methods"]),
    Rule("SK_METHOD", "method", "방법",
         re.compile(r"\b(?:in this (?:paper|work|study|article),? we|we (?:propose|present|introduce|develop|design|describe|investigate|study)"
                    r"|our (?:approach|method|model|framework|system|technique)|this (?:paper|work) (?:proposes|presents|introduces))\b", re.I),
         "제안 방법: 저자가 한 일", ["In this paper, we", "we propose", "our framework"]),
    Rule("SK_RESULT", "result", "결과",
         re.compile(r"\b(?:results? (?:show|indicate|demonstrate|suggest|reveal)|we (?:find|found|show|observe|demonstrate)"
                    r"|experiments? (?:show|demonstrate|on)|outperform\w*|achiev\w* (?:an? )?(?:new )?(?:state[- ]of[- ]the[- ]art|improvement|accuracy|f1|bleu)"
                    r"|improv\w* (?:by|over|upon)|\d+(?:\.\d+)?\s?%)", re.I),
         "결과: 실험이 보여 준 것", ["results show", "outperforms", "improves by 4.2%"]),
    Rule("SK_LIMIT", "limit", "한계",
         re.compile(r"\b(?:limitations?|future (?:work|research|directions?)|(?:does|do) not (?:generalize|address|consider)"
                    r"|remains? to be|we leave|is limited to|only (?:applies|works))\b", re.I),
         "한계·향후 과제", ["limitations", "future work", "we leave ... for"]),
]

# ---------------------------------------------------------------- 문장 난이도

PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:not\s+|\w+ly\s+)?\w+(?:ed|wn|ven|ten|ght)\b", re.I)
NOMINAL = re.compile(r"\b[a-z]{3,}(?:tion|sion|ment|ness|ity|ance|ence)s?\b", re.I)
WORDS = re.compile(r"\b[\w'-]+\b")


def difficulty(sentence: str) -> dict:
    n_words = len(WORDS.findall(sentence))
    n_passive = len(PASSIVE.findall(sentence))
    n_nominal = len(NOMINAL.findall(sentence))
    score = n_words + 6 * n_passive + 3 * n_nominal
    level = "쉬움" if score < 30 else "보통" if score < 50 else "어려움"
    return {"words": n_words, "passive": n_passive, "nominal": n_nominal, "score": score, "level": level}


# ---------------------------------------------------------------- 전체 분석


def analyze(text: str) -> dict:
    text = clean(text)
    sentences = []
    for s, e in split_sentences(text):
        sent = text[s:e]
        tags = [r for r in SKELETON_RULES if r.pattern.search(sent)]
        sentences.append({"start": s, "end": e, "text": sent, "tags": tags, "difficulty": difficulty(sent)})

    acronyms = find_acronyms(text)
    spans = []  # (start, end, category, tooltip)
    for rule in TOKEN_RULES:
        for m in rule.pattern.finditer(text):
            spans.append((m.start(), m.end(), rule.category, f"{rule.label} · 규칙 {rule.name}"))
    for abbr, long_form in acronyms.items():
        pat = re.compile(rf"\b{re.escape(abbr)}s?\b")
        for m in pat.finditer(text):
            if long_form:
                spans.append((m.start(), m.end(), "acronym", f"{abbr} = {long_form} · 규칙 ACRONYM_DEF"))
            else:
                spans.append((m.start(), m.end(), "acronym-unknown", f"{abbr}: 이 글에서 정의를 찾지 못함 · 규칙 BARE_ACRONYM"))

    # 겹치는 구간은 앞에서부터 먼저 잡힌 것(시작이 빠르고 긴 것)을 남긴다
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    kept, last_end = [], -1
    for sp in spans:
        if sp[0] >= last_end:
            kept.append(sp)
            last_end = sp[1]

    counts = {}
    for _, _, cat, _ in kept:
        counts[cat] = counts.get(cat, 0) + 1
    return {"text": text, "sentences": sentences, "acronyms": acronyms, "spans": kept, "counts": counts,
            "n_words": len(WORDS.findall(text))}
