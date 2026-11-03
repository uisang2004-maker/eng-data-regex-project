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


# ---------------------------------------------------------------- 마스킹

def protect(sentence: str, acronyms: dict[str, str | None] | None = None) -> str:
    """보호할 구간을 <x>로 감싸고 나머지는 XML 이스케이프한다."""
    pats = list(P.PROTECT_PATTERNS)
    if acronyms:
        names = sorted(acronyms, key=len, reverse=True)
        pats.insert(0, re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")s?\b"))
    spans: list[tuple[int, int]] = []
    for pat in pats:
        for m in pat.finditer(sentence):
            if m.end() > m.start() and all(m.end() <= a or m.start() >= b for a, b in spans):
                spans.append((m.start(), m.end()))
    out, pos = [], 0
    for a, b in sorted(spans):
        out += [escape(sentence[pos:a]), f"<x>{escape(sentence[a:b])}</x>"]
        pos = b
    out.append(escape(sentence[pos:]))
    return "".join(out)


def unprotect(xml_text: str) -> str:
    return unescape(P.X_TAG.sub("", xml_text))


def protected_tokens(xml_text: str) -> list[str]:
    return [unescape(t) for t in re.findall(r"<x>(.*?)</x>", xml_text)]


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
              api_key: str | None = None, caller: Caller = call_deepl, use_file_cache: bool = True) -> TranslationResult:
    """문장 목록을 번역한다. 오류가 나도 예외를 올리지 않고 TranslationResult.error에 담는다."""
    if not sentences:
        return TranslationResult(ko=[], mode="aligned", masked=masked)
    xmls = [protect(s, acronyms) if masked else escape(s) for s in sentences]
    tokens = [protected_tokens(x) for x in xmls]
    key = cache_key(xmls, masked)
    cache = _load_cache() if use_file_cache else {}
    if key in cache:
        hit = cache[key]
        return TranslationResult(ko=hit.get("ko"), mode=hit["mode"], paragraph=hit.get("paragraph"),
                                 masked=masked, cached=True, protected=tokens)

    api_key = api_key or load_api_key()
    if not api_key:
        return TranslationResult(ko=None, mode="none", masked=masked, error=NO_KEY_MESSAGE, protected=tokens)

    try:
        # 1) 문단 한 번에 + 문장 태그 → 정규식으로 복원
        joined = " ".join(f"<s>{x}</s>" for x in xmls)
        out = caller([joined], api_key, "nonewlines")[0]
        parts = P.SENT_TAG.findall(out)
        if len(parts) == len(xmls):
            ko, mode, paragraph = [fix_korean(unprotect(p)) for p in parts], "aligned", None
        else:
            # 2) 태그가 어긋나면 문장별 전송(DeepL 재분리 끔)
            outs = caller(xmls, api_key, "0")
            if len(outs) == len(xmls):
                ko, mode, paragraph = [fix_korean(unprotect(o)) for o in outs], "per_sentence", None
            else:
                # 3) 그래도 어긋나면 문단 단위로만 보여 준다
                ko, mode, paragraph = None, "paragraph", fix_korean(unprotect(re.sub(r"</?s>", "", out)))
    except TranslationError as e:
        return TranslationResult(ko=None, mode="none", masked=masked, error=str(e), protected=tokens)

    if use_file_cache:
        cache[key] = {"ko": ko, "mode": mode, "paragraph": paragraph}
        _save_cache(cache)
    return TranslationResult(ko=ko, mode=mode, paragraph=paragraph, masked=masked, protected=tokens)


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
