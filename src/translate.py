"""영어 문장 → 한국어 번역 (DeepL API Free) + 정규식 보호 마스킹.

- 보호: 약어·인용·참조·수치·URL·수식을 정규식으로 찾아 <x>…</x>로 감싸 DeepL의 ignore_tags로 보낸다.
- 정렬: 문단을 한 번에 보내되 문장마다 <s>…</s>를 씌우고, 결과에서 <s>를 정규식으로 다시 찾아 짝을 짓는다.
  태그 수가 어긋나면 문장별 전송으로 다시 시도하고, 그래도 어긋나면 문단 단위로 보여 준다.
- 호출: 화면의 버튼을 눌렀을 때만 이 모듈을 부른다. 같은 입력은 캐시로 답한다.
- 키: 저장소 루트의 .env에 DEEPL_API_KEY. 코드·로그·화면에 키 값을 내보내지 않는다.
"""

import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape, unescape

import certifi

from src import patterns as P

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "processed" / "translation_cache.json"
API_URL = "https://api-free.deepl.com/v2/translate"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

ERROR_MESSAGES = {
    429: "요청이 몰려 번역을 잠시 사용할 수 없어요. 잠시 뒤 다시 눌러 주세요.",
    456: "이번 달 DeepL 무료 한도를 다 썼어요. 번역 없이도 독해 표시는 그대로 볼 수 있어요.",
    403: "DeepL API 키를 확인할 수 없어요(.env의 DEEPL_API_KEY).",
}
NETWORK_MESSAGE = "DeepL에 연결하지 못했어요. 번역을 잠시 사용할 수 없어요."
NO_KEY_MESSAGE = "DeepL API 키가 없어 새 번역은 할 수 없어요. 저장된 예시 번역만 볼 수 있어요."


class TranslationError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


@dataclass
class TranslationResult:
    ko: list[str] | None           # 문장별 번역(mode가 aligned/per_sentence일 때 원문과 개수가 같음)
    mode: str                      # aligned(문단+태그) / per_sentence / paragraph / none
    paragraph: str | None = None   # mode가 paragraph일 때 한 덩어리 번역
    masked: bool = True
    cached: bool = False
    error: str | None = None
    protected: list[list[str]] = field(default_factory=list)   # 문장별 보호 토큰
    # 문장별 한국어 형광펜: (시작, 끝, 범주, 대응하는 영어 표현). DeepL이 옮긴 태그 위치에서 복원한다.
    ko_marks: list[list[tuple[int, int, str, str]]] = field(default_factory=list)
    # 문장별 한국어 밑줄: (시작, 끝, 카드 종류) 또는 None. 영어 밑줄을 <u>로 보내 DeepL이 옮긴 위치에서 복원한다.
    ko_underlines: list[tuple[int, int, str] | None] = field(default_factory=list)


Mark = tuple[int, int, str]   # 문장 안의 (시작, 끝, 범주)
Underline = tuple[int, int, str]   # 문장 안의 (시작, 끝, 카드 종류)


# ---------------------------------------------------------------- 마스킹·표시 태그

def _protect_spans(sentence: str, acronyms: dict[str, str | None] | None) -> list[tuple[int, int]]:
    pats = list(P.PROTECT_PATTERNS)
    if acronyms:
        names = sorted(acronyms, key=len, reverse=True)
        pats.insert(0, re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")s?\b"))
    spans: list[tuple[int, int]] = []
    for pat in pats:
        for m in pat.finditer(sentence):
            if m.end() > m.start() and all(m.end() <= a or m.start() >= b for a, b in spans):
                spans.append((m.start(), m.end()))
    return spans


def to_xml(sentence: str, acronyms: dict[str, str | None] | None = None, masked: bool = True,
           marks: list[Mark] | None = None, underline: Underline | None = None) -> str:
    """번역에 보낼 XML을 만든다.

    - masked면 보호 구간을 <x>로 감싼다(DeepL이 번역하지 않음).
    - marks(영어 쪽 형광펜)는 <m c="범주" i="번호">로 감싼다. DeepL은 이 태그를 대응하는 번역어 쪽으로 옮긴다.
      보호 구간과 겹치는 표시(약어·참조)는 <x>에 c·i 속성으로 붙인다.
    - underline(핵심 내용 밑줄)은 <u c="u-종류" i="0">로 바깥에서 감싼다. 안쪽 태그를 자르지 않도록 경계를 넓힌다.
    """
    spans: list[list] = [[a, b, "x", None, None] for a, b in (_protect_spans(sentence, acronyms) if masked else [])]
    for i, (a, b, cat) in enumerate(marks or []):
        hit = next((sp for sp in spans if not (b <= sp[0] or a >= sp[1])), None)
        if hit is not None:
            if hit[3] is None:
                hit[3], hit[4] = cat, i
        else:
            spans.append([a, b, "m", cat, i])
    spans.sort()
    ua = ub = None
    if underline and underline[1] > underline[0]:
        ua, ub = underline[0], underline[1]
        for sp in spans:   # 밑줄 경계가 다른 태그 안에 떨어지면 그 태그 바깥으로 넓혀 태그가 꼬이지 않게 한다
            if sp[0] < ua < sp[1]:
                ua = sp[0]
            if sp[0] < ub < sp[1]:
                ub = sp[1]
    cuts = sorted({0, len(sentence), *(e for sp in spans for e in sp[:2]), *((ua, ub) if ua is not None else ())})
    out = []
    for x, y in zip(cuts, cuts[1:]):
        if x == ua:
            out.append(f'<u c="u-{underline[2]}" i="0">')
        sp = next((sp for sp in spans if sp[0] == x and sp[1] == y), None)
        if sp:
            attrs = f' c="{sp[3]}" i="{sp[4]}"' if sp[3] else ""
            out.append(f"<{sp[2]}{attrs}>{escape(sentence[x:y])}</{sp[2]}>")
        else:
            out.append(escape(sentence[x:y]))
        if y == ub:
            out.append("</u>")
    return "".join(out)


def protect(sentence: str, acronyms: dict[str, str | None] | None = None) -> str:
    """보호할 구간만 <x>로 감싸고 나머지는 XML 이스케이프한다."""
    return to_xml(sentence, acronyms, masked=True)


def unprotect(xml_text: str) -> str:
    return unescape(P.X_TAG.sub("", xml_text))


def protected_tokens(xml_text: str) -> list[str]:
    return [unescape(P.X_TAG.sub("", t)) for t in re.findall(r"<x\b[^>]*>(.*?)</x>", xml_text)]


def ko_underline_from_xml(ko_xml: str, plain: str) -> tuple[int, int, str] | None:
    """번역 결과의 <u> 위치를 한국어 문장 위 구간으로 바꾼다.

    DeepL이 태그를 둘로 나누는 경우(마침표에만 붙은 조각)가 있어 글자가 가장 많은 조각을 고른다.
    밑줄 끝의 조사(을·를·은·는·에서·으로)는 밑줄 밖으로 뺀다. 찾지 못하면 None — 억지로 맞추지 않는다.
    """
    best = None
    for m in P.UL_TAG.finditer(ko_xml):
        phrase = unescape(P.X_TAG.sub("", m.group("body"))).strip()
        letters = len(re.findall(r"[가-힣A-Za-z0-9]", phrase))
        if letters and (best is None or letters > best[0]):
            best = (letters, phrase, m.group("c").removeprefix("u-"))
    if not best:
        return None
    _, phrase, kind = best
    at = plain.find(phrase)
    if at < 0:
        return None
    end = at + len(phrase)
    rest = P.KO_WORD_REST.match(plain, end).group(0)
    if rest and rest not in P.KO_NOUN_PARTICLES:              # 단어 중간에서 끝나면 단어 끝까지(조사는 제외)
        end += len(rest)
    trail = P.KO_TRAIL_PARTICLE.search(plain[at:end])
    if trail and trail.start() > 0:
        end = at + trail.start()
    return at, end, kind


def ko_marks_from_xml(ko_xml: str, plain: str, en_phrases: list[str]) -> list[tuple[int, int, str, str]]:
    """DeepL 결과의 태그 위치를 후처리된 한국어 문장(plain) 위의 구간으로 바꾼다. 못 찾은 태그는 버린다."""
    found, cursor = [], 0
    for m in P.MARK_TAG.finditer(ko_xml):
        phrase = unescape(P.X_TAG.sub("", m.group("body"))).strip()
        if not phrase:
            continue
        at = plain.find(phrase, cursor)
        if at < 0:
            at = plain.find(phrase)
        if at < 0:
            continue
        i = int(m.group("i"))
        found.append((at, at + len(phrase), m.group("c"), en_phrases[i] if i < len(en_phrases) else ""))
        cursor = at + len(phrase)
    found.sort()
    kept, last = [], -1
    for sp in found:
        if sp[0] >= last:
            kept.append(sp)
            last = sp[1]
    return kept


def fix_korean(text: str) -> str:
    """번역 후처리: 보호 참조 앞 '제' 제거, 조사 앞 공백, 인용 앞 공백."""
    text = P.KO_JE_BEFORE_REF.sub("", text)
    text = P.KO_PARTICLE_SPACE.sub("", text)
    return P.KO_SPACE_BEFORE_CITE.sub("", text).strip()


# ---------------------------------------------------------------- DeepL 호출

def load_api_key() -> str | None:
    key = os.environ.get("DEEPL_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*DEEPL_API_KEY\s*=\s*['\"]?([^'\"\s]+)", line)
            if m:
                key = m.group(1)
    return key or None


def call_deepl(texts: list[str], api_key: str, split_sentences: str) -> list[str]:
    body = json.dumps({
        "text": texts, "source_lang": "EN", "target_lang": "KO",
        "tag_handling": "xml", "ignore_tags": ["x"], "split_sentences": split_sentences,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": f"DeepL-Auth-Key {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise TranslationError(ERROR_MESSAGES.get(e.code, f"DeepL 오류(HTTP {e.code})로 번역하지 못했어요."), e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TranslationError(NETWORK_MESSAGE) from e
    return [t["text"] for t in data["translations"]]


# ---------------------------------------------------------------- 캐시

def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def cache_key(xmls: list[str], masked: bool) -> str:
    return hashlib.sha256(("M" if masked else "U").encode() + "\x1f".join(xmls).encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------- 번역

Caller = Callable[[list[str], str, str], list[str]]


def translate(sentences: list[str], acronyms: dict[str, str | None] | None = None, masked: bool = True,
              api_key: str | None = None, caller: Caller = call_deepl, use_file_cache: bool = True,
              marks: list[list[Mark]] | None = None,
              underlines: list[Underline | None] | None = None) -> TranslationResult:
    """문장 목록을 번역한다. 오류가 나도 예외를 올리지 않고 TranslationResult.error에 담는다.

    marks를 주면(문장별 영어 형광펜 구간) 한국어 쪽 형광펜 위치(ko_marks)도,
    underlines를 주면(문장별 핵심 내용 밑줄) 한국어 쪽 밑줄 위치(ko_underlines)도 함께 돌려준다.
    """
    if not sentences:
        return TranslationResult(ko=[], mode="aligned", masked=masked)
    marks = marks or [[] for _ in sentences]
    underlines = underlines or [None for _ in sentences]
    xmls = [to_xml(s, acronyms, masked, mk, ul) for s, mk, ul in zip(sentences, marks, underlines)]
    tokens = [protected_tokens(x) if masked else [] for x in xmls]
    en_phrases = [[s[a:b] for a, b, _ in mk] for s, mk in zip(sentences, marks)]
    key = cache_key(xmls, masked)
    cache = _load_cache() if use_file_cache else {}
    def finish(raw: list[str]) -> tuple[list[str], list, list]:
        ko = [fix_korean(unprotect(r)) for r in raw]
        return (ko, [ko_marks_from_xml(r, k, e) for r, k, e in zip(raw, ko, en_phrases)],
                [ko_underline_from_xml(r, k) if ul else None for r, k, ul in zip(raw, ko, underlines)])

    if key in cache and cache[key].get("raw"):
        # DeepL 원본 응답을 저장해 두었으면 후처리 규칙이 바뀌어도 다시 호출하지 않고 다시 계산한다
        hit = cache[key]
        ko, km, ku = finish(hit["raw"])
        return TranslationResult(ko=ko, mode=hit["mode"], masked=masked, cached=True, protected=tokens,
                                 ko_marks=km, ko_underlines=ku)
    if key in cache:
        hit = cache[key]
        return TranslationResult(ko=hit.get("ko"), mode=hit["mode"], paragraph=hit.get("paragraph"), masked=masked,
                                 cached=True, protected=tokens,
                                 ko_marks=[[tuple(x) for x in row] for row in hit.get("ko_marks", [])],
                                 ko_underlines=[tuple(u) if u else None for u in hit.get("ko_underlines", [])])

    api_key = api_key or load_api_key()
    if not api_key:
        return TranslationResult(ko=None, mode="none", masked=masked, error=NO_KEY_MESSAGE, protected=tokens)

    ko_marks: list = []
    raw_parts: list[str] | None = None
    ko_underlines: list = []
    try:
        # 1) 문단 한 번에 + 문장 태그 → 정규식으로 복원
        joined = " ".join(f"<s>{x}</s>" for x in xmls)
        out = caller([joined], api_key, "nonewlines")[0]
        parts = P.SENT_TAG.findall(out)
        if len(parts) == len(xmls):
            (ko, ko_marks, ko_underlines), mode, paragraph, raw_parts = finish(parts), "aligned", None, parts
        else:
            # 2) 태그가 어긋나면 문장별 전송(DeepL 재분리 끔)
            outs = caller(xmls, api_key, "0")
            if len(outs) == len(xmls):
                (ko, ko_marks, ko_underlines), mode, paragraph, raw_parts = finish(outs), "per_sentence", None, outs
            else:
                # 3) 그래도 어긋나면 문단 단위로만 보여 준다(형광펜 없음)
                ko, mode, paragraph = None, "paragraph", fix_korean(unprotect(re.sub(r"</?s>", "", out)))
    except TranslationError as e:
        return TranslationResult(ko=None, mode="none", masked=masked, error=str(e), protected=tokens)

    if use_file_cache:
        cache[key] = {"ko": ko, "mode": mode, "paragraph": paragraph, "ko_marks": ko_marks,
                      "ko_underlines": ko_underlines, "raw": raw_parts}
        _save_cache(cache)
    return TranslationResult(ko=ko, mode=mode, paragraph=paragraph, masked=masked, protected=tokens, ko_marks=ko_marks,
                             ko_underlines=ko_underlines)


def preserved_ratio(result: TranslationResult) -> tuple[int, int]:
    """보호 대상 토큰 중 번역문에 그대로 남은 수 / 전체 수(문장별 정렬 결과 기준)."""
    if not result.ko:
        return 0, 0
    total = kept = 0
    for toks, ko in zip(result.protected, result.ko):
        for t in toks:
            total += 1
            kept += t in ko
    return kept, total
