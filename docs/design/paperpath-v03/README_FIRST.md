# PaperPath 개발 인계 패키지

**디자인 기준:** v03 확정본  
**기획 기준:** 2026-11-04 4차 개정 기획서  
**목적:** 개발 AI 또는 개발자에게 전달해 실제 Streamlit 앱을 구현하기 위한 인계 자료

## 먼저 읽을 파일

1. `DEVELOPMENT_HANDOFF.md` — 화면·동작·기술 구조·검수 기준을 포함한 상세 명세
2. `PROMPT_FOR_DEV_AI.md` — 개발 AI에게 그대로 전달할 작업 지시문
3. `references/paperpath-v03-approved.png` — 확정된 데스크톱 화면 캡처(1440×900)
4. `references/index-v03-visual-reference.html` — 정적 화면의 HTML/CSS 참고본
5. `references/PLAN-4th-revision-2026-11-04.md` — 기능·범위의 원본 기획서

## 기준 충돌 시 우선순위

- **화면의 외형·배치·스타일:** `paperpath-v03-approved.png`와 `index-v03-visual-reference.html`
- **실제 기능·규칙·데이터·오류 처리·범위:** `PLAN-4th-revision-2026-11-04.md`
- 이 인계 문서: 두 기준을 구현 관점에서 연결하고, 목업에 없는 동작을 명시

v03 HTML은 디자인 참고용 정적 목업입니다. 실제 API, 정규식 분석, 상태 관리가 연결되어 있다고 간주하면 안 됩니다.
