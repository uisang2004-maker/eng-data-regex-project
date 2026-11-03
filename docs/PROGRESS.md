# 진행 기록 (PROGRESS)

## 현재 상태

- **현재 Phase**: Phase 2 — 예비 사이트 구현 (아이디어 3 「논문 독해 도우미」 프로토타입 1차 완료, 컨펌 전)
- **마감**: 12월 초 (약 4주, 잠정 2026-12-01 기준 남은 28일) — **정확한 제출일/발표일 미확정**
- **저장소**: https://github.com/uisang2004-maker/eng-data-regex-project (비공개)

## 확정된 결정

| 날짜 | 결정 |
|---|---|
| 2026-11-03 | 저장소 이름 `eng-data-regex-project`, 비공개로 생성. 공개 전환은 발표 직전에 결정 |
| 2026-11-03 | 마감은 12월 초(약 4주)로 잡고 범위를 정함 |
| 2026-11-03 | 아이디어 3을 「논문 독해 도우미」로 확장해 프로토타입 진행 (컨펌 아님) |

## 남은 일

- [ ] 정확한 제출일·발표일 확인 (이의상)
- [x] Phase 1: 아이디어 후보 3개 작성 → `docs/ideas/` (1차, 2026-11-03)
- [x] 이의상: 후보 선택 → 아이디어 3을 「논문 독해 도우미」로 확장해 진행 (2026-11-03)
- [x] Phase 2: `prototype/paper-reader/` 1차 구현 (2026-11-03)
- [ ] 이의상: 프로토타입 피드백 / 컨펌 여부
- [ ] 컨펌 게이트

## 일지

### 2026-11-03

1. Phase 0 완료. 비공개 저장소 생성, 기본 폴더 구조·`.gitignore`·`.gitattributes`·README·이 파일 작성.
2. 파일: `README.md`, `docs/PROGRESS.md`, `.gitignore`, `.gitattributes`, 각 폴더 `.gitkeep`.
3. 테스트: 코드 없음(해당 없음). 환경 확인: `gh` 로그인 정상, Python 3.14.7(`py -I`).
4. 막힌 것: 없음.
5. 이의상 님 할 일: 정확한 마감일 알려 주기, 아이디어 방향 피드백.

### 2026-11-03 (2)

1. Phase 1 1차 후보 3개 작성. 점수(합계/25): ① 약관 레드플래그 탐지기 22 ② 레시피 분량·단위 변환기 22 ③ 논문 약어 X-ray 20. 동점은 시연 임팩트로 정해 ①을 우선 추천.
2. 파일: `docs/ideas/idea-1-tos-redflag.md`, `idea-2-recipe-scaler.md`, `idea-3-paper-acronym-xray.md`.
3. 실행: 후보별 핵심 regex를 예시 문장으로 Python에서 실행해 매칭을 확인함(임시 스크립트, 저장소 밖). idea-3의 4번 패턴은 미실행. pytest는 코드 없음(해당 없음).
4. 출처 확인: arXiv API 이용약관(메타데이터 CC0, 3초/1회)과 Gutenberg robot 정책(자동 접근 금지, 수동 다운로드)은 원문으로 확인함. ToS;DR 라이선스(CC BY-SA 3.0)는 2차 출처로만 확인함.
5. 이의상 님 할 일: 예비 사이트로 만들 후보 고르기, 정확한 마감일 알려 주기.

### 2026-11-03 (3)

1. Phase 2로 진행. 사용자 논의(논문 읽기가 어려운 5가지 이유, 기존 서비스 조사, 독해 도구의 입력 범위)를 반영해 idea-3을 「논문 독해 도우미」로 개정함. 독해 도구는 붙여 넣는 텍스트 전부를 받고, 대량 분석은 CC0 초록만 다루는 범위.
2. 파일: `docs/ideas/idea-3-paper-reading-helper.md`(이름 변경·개정), `prototype/paper-reader/`(rules.py, app.py, fetch_sample.py, README.md, data/sample_abstracts.jsonl), `requirements.txt`, `.gitignore`.
3. 실행: arXiv API로 cs.CL 초록 300건 수집 성공(연도 6개 × 50건). 처음에는 Windows 인증서 오류가 나서 certifi로 해결함. Streamlit 1.66.1을 로컬에서 실행해 탭 3개를 브라우저로 확인했고 서버 오류는 없었음. 샘플 지표(연도별 평균): 초록당 약어 정의 수 2012년 0.22 → 2025년 1.04, 정의 없는 약어 0.70 → 2.50. pytest는 아직 없음(Phase 3에서 작성).
4. 막힌 것: 없음. 알려진 한계는 prototype/paper-reader/README.md에 적음.
5. 이의상 님 할 일: 프로토타입을 써 보고 피드백 주기 / 컨펌 여부 결정, 정확한 마감일 알려 주기.
