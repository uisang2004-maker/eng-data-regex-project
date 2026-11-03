"""평가 지표 계산: 3줄 뼈대 검출·채움률, 마스킹 on/off 실측.

결과는 '검증 결과' 탭과 README에 쓴다. 측정하지 않은 값은 만들지 않는다.
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path

from src import patterns as P
from src.extract import analyze
from src.translate import call_deepl, load_api_key, protect, protected_tokens, translate

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "data" / "processed" / "masking_benchmark.json"


def skeleton_stats(rows: list[dict]) -> dict:
    """신호 문구만 쓸 때와 위치 대체를 켰을 때의 카드별 근거 분포."""
    no_fallback = P.DEFAULT_ACTIVE_RULES - {"SK_FALLBACK"}
    out = {"n": len(rows)}
    for name, active in (("signal_only", no_fallback), ("with_fallback", P.DEFAULT_ACTIVE_RULES)):
        basis = Counter()
        all_filled = 0
        for r in rows:
            cards = analyze(r["abstract"], active).skeleton
            for c in cards:
                basis[(c.kind, c.basis)] += 1
            all_filled += all(c.basis != "none" for c in cards)
        out[name] = {
            "all_three_filled": all_filled,
            "by_card": {f"{k}:{b}": v for (k, b), v in sorted(basis.items())},
        }
    return out


def masking_benchmark(rows: list[dict], n: int = 30, caller=call_deepl, api_key: str | None = None) -> dict:
    """초록 n편을 마스킹 켬/끔으로 번역해 보호 대상 토큰이 번역문에 그대로 남는 비율을 잰다.

    보호 대상 토큰은 마스킹 켬 기준(protect)으로 정한다. 끔 결과에서도 같은 토큰이 남았는지 센다.
    """
    api_key = api_key or load_api_key()
    papers = []
    step = max(1, len(rows) // n)   # 연도별로 고르게 뽑는다(샘플은 연도순)
    for r in rows[::step][:n]:
        a = analyze(r["abstract"])
        sents = [s.text for s in a.sentences]
        toks = [protected_tokens(protect(s, a.acronyms)) for s in sents]
        row = {"id": r.get("id"), "tokens": sum(len(t) for t in toks)}
        for masked in (True, False):
            res = translate(sents, a.acronyms, masked=masked, api_key=api_key, caller=caller)
            key = "on" if masked else "off"
            if res.ko is None:
                row[key] = {"error": res.error, "mode": res.mode}
                continue
            kept = sum(t in ko for ts, ko in zip(toks, res.ko) for t in ts)
            lost = [t for ts, ko in zip(toks, res.ko) for t in ts if t not in ko]
            row[key] = {"kept": kept, "mode": res.mode, "lost": lost}
        papers.append(row)
    total = sum(p["tokens"] for p in papers)
    summary = {"date": date.today().isoformat(), "papers": len(papers), "tokens": total}
    for key in ("on", "off"):
        ok = [p for p in papers if "kept" in p.get(key, {})]
        summary[f"{key}_kept"] = sum(p[key]["kept"] for p in ok)
        summary[f"{key}_papers_ok"] = len(ok)
    return {"summary": summary, "papers": papers}


def load_benchmark() -> dict | None:
    try:
        return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    # 2주차 실측: .venv/Scripts/python.exe -m src.analyze  (DeepL 약 4만 자 사용)
    from src.collect import load_samples
    result = masking_benchmark(load_samples())
    BENCHMARK_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(result["summary"])
