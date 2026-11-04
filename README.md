# PaperPath — 처음 읽는 영어 논문 도우미

「영어데이터 처리를 위한 프로그래밍」(Regular Expression with Python) 기말 프로젝트입니다.

영어 논문 초록이나 단락을 넣으면 **정규표현식이** 먼저 읽을 문장 3개(문제·방법·결과)를 원문에서 고르고, 약어·추측·확신·참조 표현을 근거와 함께 표시합니다. 필요하면 한국어 번역을 문장 단위로 옆에 켭니다. AI가 대신 요약하지 않습니다. **읽는 길은 정규식이, 판단은 학생이.**

> **공개 사이트: https://paperpath-hufs.streamlit.app/** (Streamlit Community Cloud, 2026-11-04 배포)
>
> 현재 상태: **Phase 3 (구현 중)** · 마감 2026-11-30 · 진행 기록은 [docs/PROGRESS.md](docs/PROGRESS.md), 계획은 [docs/PLAN.md](docs/PLAN.md)를 보세요.

![PaperPath 첫 화면](docs/screenshots/phase3-desktop-1440x900.jpg)

## 실행 방법

Windows(Git Bash) 기준입니다. Python 3.14에서 확인했습니다.

```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run app.py
```

브라우저에서 `http://localhost:8501`이 열립니다.

### 번역(선택)

번역 엔진은 두 가지입니다. `ANTHROPIC_API_KEY`가 있으면 **Claude Haiku 5.5**(`claude-haiku-5-5`, AI 번역, 유료)를 쓰고, 없으면 **DeepL API Free**를 씁니다. 두 엔진 모두 같은 태그 방식(보호 `<x>`, 형광펜 `<m>`, 밑줄 `<u>`, 문장 `<s>`)으로 보내고 정규식으로 복원합니다. 키가 없어도 정규식 기능은 모두 동작하고, 예시 문단은 저장된 번역으로 볼 수 있습니다.

1. `cp .env.example .env`
2. `.env`에 `ANTHROPIC_API_KEY=<본인 키>` 또는 `DEEPL_API_KEY=<본인 키>`를 적습니다. **`.env`는 커밋되지 않습니다.**
3. 번역은 화면의 **번역하기** 버튼을 눌렀을 때만 호출됩니다. 입력한 영어 문장이 고른 번역 서비스로 전송됩니다.

Claude API 키는 [console.anthropic.com](https://console.anthropic.com)에서 만들며 무료 등급이 없습니다. 콘솔의 월 사용 한도(spend limit)를 낮게 걸어 두는 것을 권장합니다. Haiku 5.5 요금은 입력 100만 토큰당 $0.10, 출력 $0.50입니다.

### 공개 사이트로 배포 (Streamlit Community Cloud)

1. [share.streamlit.io](https://share.streamlit.io)에 GitHub 계정으로 로그인합니다.
2. **Create app** → **Yup, I have an app** → 저장소 `uisang2004-maker/eng-data-regex-project`, 브랜치 `main`, 파일 `app.py`를 고릅니다.
3. **Advanced settings**에서 Python 3.12를 고르고, **Secrets** 칸에 `ANTHROPIC_API_KEY = "본인 키"`(또는 `DEEPL_API_KEY = "본인 키"`)를 적습니다. 키는 이 칸에만 적고 저장소에는 넣지 않습니다.
4. **Deploy**를 누릅니다. 비공개 저장소에서 만든 앱은 처음에 비공개라서, 앱의 **Share → Make this app public**으로 공개합니다.

공개 사이트의 번역은 비용과 무료 한도를 지키기 위해 제한됩니다([src/usage.py](src/usage.py)).
- 한 번에 3,000자까지
- 한 화면(세션)당 10회
- 사이트 전체 하루 30,000자

하루 사용량은 서버 파일로 세기 때문에, 서버가 재시작되면 다시 0부터 셀 수 있습니다. 실제 기준은 번역 서비스 계정(Anthropic 콘솔·DeepL)의 사용량입니다.

### 테스트

```bash
.venv/Scripts/python.exe -I -m pytest -q
```

### 데이터 재현

```bash
.venv/Scripts/python.exe -m src.collect
```

arXiv cs.CL 초록을 연도별(2012·2015·2018·2021·2024·2025) 50편씩 받아 `data/processed/sample_abstracts.jsonl`에 저장합니다. 요청 사이에 3초를 두고, 저자 필드는 저장하지 않습니다.

## 화면

| 탭 | 내용 |
|---|---|
| 논문 읽기 | arXiv ID 또는 텍스트 입력 → 3줄 뼈대 → 원문 하이라이트·번역 → 약어·규칙 근거 |
| 규칙 탐색 | 처리 단계, 준비된 규칙 켜고 끄기(자유 정규식 입력은 없음), 규칙별 패턴·예시·놓치는 경우 |
| 검증 결과 | 측정한 값과 목표·예정을 구분해 표시 |

## 핵심 정규식

모든 규칙은 [src/patterns.py](src/patterns.py)에 있고, 패턴마다 잡는 것·예시·일부러 놓치는 경우를 적었습니다.

| 기능 | 정규식이 하는 일 |
|---|---|
| 입력 정리 | 줄바꿈·연속 공백·줄 끝 하이픈·쪽번호 줄·반복 머리말 정리 |
| 문장 분리 | `e.g.`·`et al.`·`Fig.` 같은 약어, 수식·인용·URL 안의 마침표에서 자르지 않음 |
| 약어 | 괄호 안 약어 후보를 정규식으로 찾고, 앞 단어 첫 글자와 Python 함수로 맞춤 |
| 3줄 뼈대 | 문제·방법·결과 신호 문구. 없으면 위치로 대체하고 "추정"이라고 표시 |
| 추측·확신·참조 | `may`·`suggest` 등(가능·허용 뜻은 제외), `significantly` 등, `[4]`·`(Smith et al., 2021)`·`Table 2` |
| 번역 보호 | 약어·인용·참조를 `<x>`로 감싸 번역에서 보호하고, 문장마다 `<s>` 태그로 영한 짝을 복원. 수치는 실측 결과 보호하지 않음([docs/MASKING_BENCHMARK.md](docs/MASKING_BENCHMARK.md)) |
| 번역문 형광펜 | 영어 형광펜을 `<m>` 태그로 감싸 보내고, 번역기가 옮긴 태그를 정규식으로 찾아 한국어 문장에도 같은 색을 칠함 |
| 핵심 내용 밑줄 | 형광펜이 신호라면 밑줄은 내용. 3줄 뼈대 문장에서 신호 문구가 가리키는 구간(12단어 이내)에 밑줄을 긋고, 번역문과 카드 아래 번역에도 옮김 |
| 용어 설명·수치 | `refers to`·`, which is …`·`such as`·`(i.e., …)`·동격(`X, a …,`) 뒤의 설명 구간에 점선 밑줄, `8.4%`·`accuracy of 74%` 같은 수치 근거에 형광펜 |
| 반복 용어 | 이 글에서 3번 이상 나오는 용어(기능어·일반어 제외, 두 단어 용어 우선)에 굵은 글씨와 얇은 밑줄 |
| 흐름도·어려운 단어표 | 문장 역할(배경→문제→방법→결과→한계)을 이은 흐름도, 일상 영어에서 드문 단어(전문용어)·약어·모델 이름을 난이도와 함께 모은 단어표(CSV 내려받기) |

## 폴더 구조

| 경로 | 용도 |
|---|---|
| `app.py` | Streamlit 화면 |
| `src/` | `patterns`(규칙) · `clean`(정리·분리) · `extract`(약어·뼈대·표시) · `collect`(arXiv) · `translate`(Claude Haiku·DeepL) · `analyze`(평가) |
| `tests/` | pytest(규칙 양성·음성·경계 사례, 번역 안전장치, 화면 상태) |
| `data/processed/` | 초록 샘플(CC0), arXiv·번역 캐시 |
| `docs/` | 계획서, 진행 기록, 체크리스트, 디자인 인계 자료(`design/paperpath-v03`), 스크린샷 |
| `prototype/` | Phase 2 프로토타입(기록용) |

## 데이터와 개인정보

- 어려운 단어 판정에는 [wordfreq](https://github.com/rspeer/wordfreq) 3.1.1의 영어 단어 빈도를 씁니다(`data/processed/en_word_zipf.tsv`, 데이터 라이선스 CC BY-SA 4.0, 원 출처에 Google Books Ngrams·SUBTLEX 등 포함).

- arXiv 메타데이터(제목·초록)는 CC0 1.0입니다. 저자 정보는 수집하지 않습니다.
- 붙여 넣은 텍스트와 그 번역은 저장하지 않습니다. 예시 문단과 arXiv 초록의 번역만 캐시 파일에 남깁니다.
- 번역 서비스(Anthropic·DeepL) 측의 데이터 보관은 각 서비스의 약관을 따르며, 이 앱이 따로 확인하지는 못했습니다. 번역 전에 화면에서 전송 사실을 안내합니다.

## 한계

- 샘플은 연도별 연말 최신 제출 50편이라 대표성이 없습니다.
- `XGBoost`·`BiLSTM`·`k-NN` 같은 약어는 풀네임을 찾지 못합니다(틀린 풀네임을 만들지 않고 "정의를 찾지 못함"으로 표시).
- 추측 표시는 조동사 자체를 표시하며, 문장을 넘는 문맥은 보지 않습니다.
- 번역은 말투(~습니다/~한다)가 섞일 수 있습니다. AI 번역(Claude)은 드물게 뜻을 바꾸거나 빼먹을 수 있어 참고용입니다.
- PDF 2단 편집 순서는 복원하지 않습니다. arXiv ID 입력을 권장합니다.

## AI 도구 사용

- **Claude Code(Anthropic):** 기획 문서 초안, 정규식·코드·테스트 작성 보조에 사용했습니다. 모든 결정과 컨펌은 이의상이 했고, 테스트는 실제로 실행한 결과만 기록했습니다.
- **Claude Haiku 5.5(Anthropic API) / DeepL API Free:** 화면의 선택 기능인 영→한 번역에만 사용합니다. 3줄 뼈대·형광펜·밑줄·단어표는 모두 정규식 결과이고 AI가 만들지 않습니다.
- 화면 디자인(v03)은 별도로 만든 디자인 인계 자료(`docs/design/paperpath-v03`)를 기준으로 구현했습니다.
