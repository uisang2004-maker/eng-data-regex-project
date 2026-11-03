# 논문 독해 도우미 — Phase 2 프로토타입

아이디어 검증용 시연 사이트다. 설계 문서는 [docs/ideas/idea-3-paper-reading-helper.md](../../docs/ideas/idea-3-paper-reading-helper.md)에 있다.

## 실행

```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run prototype/paper-reader/app.py
```

## 구성

| 파일 | 내용 |
|---|---|
| `rules.py` | 정규표현식 규칙 전부: 전처리, 문장 분리, 약어, 추측·확신, 참조, 뼈대 문장, 난이도 |
| `app.py` | Streamlit 화면. 탭 세 개: 독해 도우미, 샘플 분석, 규칙 보기 |
| `translate.py` | 영→한 번역(DeepL API Free). 약어·인용·참조·수치를 regex로 `<x>` 마스킹해 번역에서 보호하고, 결과를 `data/translation_cache.json`에 캐시한다. 아직 화면에 연결하지 않음 |
| `fetch_sample.py` | arXiv API로 cs.CL 초록 샘플을 수집한다 (연도별 50건, 3.5초 간격) |
| `data/sample_abstracts.jsonl` | 수집한 샘플 300건 (id, 연도, 제목, 초록만 저장. 메타데이터 CC0 1.0) |

## 알려진 한계 (프로토타입)

- 샘플은 각 연도 말에 제출된 최신 50건이라 대표성이 없다
- `VISION`, `CAMBRIAN`처럼 강조용 대문자 단어도 "정의 없는 약어"로 센다
- `MedQA`는 정의했어도, 그 안의 `QA`를 별도 미정의 약어로 센다
- 난이도 점수 기준(30/50)은 임시값이다
- 테스트는 없다. 컨펌 후 Phase 3에서 `src/patterns.py`와 pytest로 옮긴다
