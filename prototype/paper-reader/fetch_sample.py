"""arXiv API에서 연도별 cs.CL 초록 샘플을 받아 JSONL로 저장한다.

- arXiv 메타데이터(제목·초록)는 CC0 1.0이다. 저자 필드는 저장하지 않는다.
- API 이용약관에 따라 요청 사이에 3초 이상 쉰다.

실행: .venv/Scripts/python.exe prototype/paper-reader/fetch_sample.py
"""

import json
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import certifi

API = "https://export.arxiv.org/api/query"
YEARS = [2012, 2015, 2018, 2021, 2024, 2025]
PER_YEAR = 50
OUT = Path(__file__).parent / "data" / "sample_abstracts.jsonl"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())
NS = {"a": "http://www.w3.org/2005/Atom"}


def fetch_year(year: int) -> list[dict]:
    query = f"cat:cs.CL AND submittedDate:[{year}01010000 TO {year}12312359]"
    params = urllib.parse.urlencode(
        {"search_query": query, "start": 0, "max_results": PER_YEAR,
         "sortBy": "submittedDate", "sortOrder": "descending"}
    )
    req = urllib.request.Request(
        f"{API}?{params}", headers={"User-Agent": "eng-data-regex-project (course project)"}
    )
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        root = ET.fromstring(resp.read())
    rows = []
    for entry in root.findall("a:entry", NS):
        rows.append({
            "id": entry.findtext("a:id", namespaces=NS).rsplit("/", 1)[-1],
            "year": year,
            "title": " ".join(entry.findtext("a:title", namespaces=NS).split()),
            "abstract": entry.findtext("a:summary", namespaces=NS).strip(),
        })
    return rows


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, year in enumerate(YEARS):
        if i:
            time.sleep(3.5)
        got = fetch_year(year)
        print(f"{year}: {len(got)}건")
        rows.extend(got)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"저장: {OUT} ({len(rows)}건)")


if __name__ == "__main__":
    main()
