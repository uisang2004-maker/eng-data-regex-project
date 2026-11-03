"""영어 문장 → 한국어 번역 (DeepL API Free) + 정규식 번역 보호 마스킹.

번역 엔진이 망가뜨리기 쉬운 토큰(약어, 인용, 그림·표 참조, 수치, URL)을
정규식으로 찾아 <x>...</x>로 감싼 뒤 DeepL의 ignore_tags=x로 보낸다.
DeepL은 <x> 안의 텍스트를 번역하지 않는다(tag_handling=xml).

- API 키는 저장소 루트의 .env에 DEEPL_API_KEY=...:fx 로 둔다(커밋 금지).
- 같은 문장은 data/translation_cache.json에 캐시해 한도를 아끼고 오프라인 시연을 가능하게 한다.
"""

import hashlib
import json
import os
import re
import ssl
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape, unescape

import certifi

import rules

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = Path(__file__).parent / "data" / "translation_cache.json"
API_URL = "https://api-free.deepl.com/v2/translate"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# 번역하면 안 되는 토큰 (앞에 있을수록 우선)
PROTECT_PATTERNS = [
    re.compile(r"https?://\S+"),
    re.compile(r"\[math\]"),
    *[r.pattern for r in rules.TOKEN_RULES if r.category == "ref"],
    # 수치: 4.2%, 87 %, 0.05, 1,000, 3x
    re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?:\s?%|x\b)?"),
]
X_TAG = re.compile(r"</?x>")
# 번역 후처리: DeepL이 보호된 참조 앞에 붙이는 "제"(예: "제Section 5.1") 제거
KO_FIXES = [(re.compile(r"제\s?(?=(?:Sec(?:tion)?|Table|Fig(?:ure)?|Eq|Appendix|Alg)\b)"), "")]


def fix_korean(text: str) -> str:
    for pat, rep in KO_FIXES:
        text = pat.sub(rep, text)
    return text


def protect(sentence: str, acronyms: dict[str, str | None]) -> str:
    """보호할 구간을 <x>로 감싸고 나머지는 XML 이스케이프한 문자열을 돌려준다."""
    patterns = list(PROTECT_PATTERNS)
    if acronyms:
        names = sorted(acronyms, key=len, reverse=True)
        patterns.insert(0, re.compile(r"\b(?:" + "|".join(re.escape(a) for a in names) + r")s?\b"))
    spans = []
    for pat in patterns:
        for m in pat.finditer(sentence):
            if m.end() > m.start() and all(m.end() <= a or m.start() >= b for a, b in spans):
                spans.append((m.start(), m.end()))
    spans.sort()
    out, pos = [], 0
    for a, b in spans:
        out.append(escape(sentence[pos:a]))
        out.append(f"<x>{escape(sentence[a:b])}</x>")
        pos = b
    out.append(escape(sentence[pos:]))
    return "".join(out)


def unprotect(xml_text: str) -> str:
    return unescape(X_TAG.sub("", xml_text))


def protected_tokens(xml_text: str) -> list[str]:
    return [unescape(t) for t in re.findall(r"<x>(.*?)</x>", xml_text)]


def load_api_key() -> str | None:
    key = os.environ.get("DEEPL_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*DEEPL_API_KEY\s*=\s*['\"]?([^'\"\s]+)", line)
            if m:
                key = m.group(1)
    return key or None


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def _call_deepl(xml_texts: list[str], api_key: str) -> list[str]:
    body = json.dumps({
        "text": xml_texts, "source_lang": "EN", "target_lang": "KO",
        "tag_handling": "xml", "ignore_tags": ["x"], "split_sentences": "0",
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": f"DeepL-Auth-Key {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        data = json.loads(resp.read())
    return [t["text"] for t in data["translations"]]


def translate_sentences(sentences: list[str], acronyms: dict[str, str | None],
                        api_key: str | None = None, allow_api: bool = True) -> list[dict]:
    """문장마다 {en, ko, protected, cached} 를 돌려준다. 번역할 수 없으면 ko=None."""
    cache = _load_cache()
    xmls = [protect(s, acronyms) for s in sentences]
    keys = [hashlib.sha256(x.encode("utf-8")).hexdigest()[:16] for x in xmls]
    missing = [i for i, k in enumerate(keys) if k not in cache]
    api_key = api_key or load_api_key()
    if missing and allow_api and api_key:
        results = _call_deepl([xmls[i] for i in missing], api_key)
        for i, ko_xml in zip(missing, results):
            cache[keys[i]] = {"en_xml": xmls[i], "ko_xml": ko_xml}
        _save_cache(cache)
    out = []
    for s, x, k in zip(sentences, xmls, keys):
        hit = cache.get(k)
        out.append({"en": s, "ko": fix_korean(unprotect(hit["ko_xml"])) if hit else None,
                    "protected": protected_tokens(x), "cached": k not in [keys[i] for i in missing]})
    return out
