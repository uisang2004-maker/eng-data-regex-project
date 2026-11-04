"""PaperPath — 처음 읽는 영어 논문 도우미 (Streamlit).

실행: .venv/Scripts/python.exe -m streamlit run app.py
외형은 docs/design/paperpath-v03, 기능은 docs/PLAN.md를 따른다.
"""

import hashlib
import html

import streamlit as st

from src import patterns as P
from src import translate as T
from src import usage
from src.analyze import load_benchmark, skeleton_stats
from src.collect import ArxivError, fetch_abstract, load_samples
from src import glossary as G
from src.extract import ROLE_ORDER, analyze

PAGES = ("논문 읽기", "규칙 탐색", "검증 결과")
MODES = ("arXiv ID", "텍스트 붙여 넣기")
MAX_PASTE = 20000

# 화면 예시용으로 직접 작성한 문단(실제 논문 아님). v03 시안과 같은 문장이다.
DEMO_TEXT = (
    "Retrieval-augmented generation (RAG) can ground language models in external documents, but selecting "
    "reliable evidence remains challenging. To address this issue, we introduce a lightweight reranking module "
    "that scores retrieved passages using contextual relevance. Experiments on three public benchmarks show that "
    "the proposed module significantly improves retrieval precision by 8.4% compared with the baseline. These "
    "findings suggest that a compact reranker may help smaller models use evidence more consistently [4]."
)
RULE_DEMO = "The method may be applied to images, and the results suggest a gain over BERT [4]."

KIND_META = {
    "problem": ("문제 · Problem", "blue"),
    "method": ("방법 · Method", "teal"),
    "result": ("결과 · Result", "violet"),
}
BASIS_TEXT = {"signal": "신호 문구로 찾음", "position": "위치로 추정", "none": "찾지 못함"}
MARK_LABEL = {"abbr": "약어", "abbr-missing": "약어(정의 없음)", "hedge": "추측·가능성", "confident": "확신", "reference": "참조",
              "definition": "용어 설명·예시", "number": "수치 근거", "term": "반복 용어"}
CAT_RULE = {"abbr": "ABBR", "abbr-missing": "ABBR", "hedge": "HEDGE", "confident": "CONFIDENT", "reference": "REFERENCE",
            "definition": "DEFINITION", "number": "NUMBER", "term": "TERM"}
UL_TITLE = {"problem": "핵심 내용(밑줄) · 무엇이 어려운가", "method": "핵심 내용(밑줄) · 무엇을 만들었나",
            "result": "핵심 내용(밑줄) · 무엇을 발견했나", "def": "용어 설명(점선 밑줄)"}

ICON = {
    "doc": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/></svg>',
    "search": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6"/><path d="m20 20-4-4M11 8v6M8 11h6"/></svg>',
    "shield": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
    "info": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
    "list": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 7h14M5 12h9M5 17h11"/><circle cx="18" cy="17" r="2"/></svg>',
    "rule": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m4 18 5-12 4 9 3-5 4 8"/></svg>',
}

CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
:root {
  --ink:#14263e; --muted:#52677f; --subtle:#66798b; --line:#e2e9f2; --surface:#ffffff; --canvas:#f6f8fc;
  --navy:#183b60; --blue:#2b6f9f; --blue-soft:#edf5fc; --teal:#21877f; --teal-soft:#eaf7f4;
  --amber:#9a681d; --amber-soft:#fff7e8; --violet:#7156a2; --violet-soft:#f3effa;
  --radius:14px; --shadow:0 4px 18px rgba(26,54,83,.045), 0 1px 2px rgba(25,49,77,.03);
}
html, body, [data-testid="stAppViewContainer"], .stApp {
  background: radial-gradient(780px 300px at 88% -8%, rgba(216,232,247,.46), transparent 70%),
              linear-gradient(180deg,#f8fafd 0%,#f4f7fb 100%) !important;
  color: var(--ink);
  font-family: Pretendard, "Malgun Gothic", "Segoe UI", sans-serif;
}
.stApp * { font-family: Pretendard, "Malgun Gothic", "Segoe UI", sans-serif; }
.stApp [data-testid="stIconMaterial"], .stApp [data-testid="stIconMaterial"] * { font-family: "Material Symbols Rounded" !important; }
code, pre, .pp-code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace !important; }
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
.block-container { max-width: 1320px !important; padding: 0 16px 40px !important; }
[data-testid="stVerticalBlock"] { gap: .75rem; }

/* 상단 바 */
.stApp, [data-testid="stMain"], [data-testid="stAppViewContainer"] { overflow-x: hidden; }
.st-key-topbar { position: relative; padding: 10px 0; margin-bottom: 6px; }
.st-key-topbar::before { content:""; position:absolute; top:0; bottom:0; left:-100vw; right:-100vw; z-index:0;
  background: rgba(255,255,255,.94); border-bottom: 1px solid #e4eaf2; box-shadow: 0 2px 12px rgba(22,46,74,.025); }
.st-key-topbar > div { position: relative; z-index: 1; }
.pp-brand { display:flex; align-items:center; gap:12px; min-height:46px; }
.pp-mark { width:38px; height:38px; border-radius:12px; display:grid; place-items:center; color:#fff;
  background: linear-gradient(145deg,#214d75 0%,#142f4f 100%); box-shadow:0 5px 12px rgba(24,59,96,.18); flex:none; }
.pp-name { font-size:16px; font-weight:750; letter-spacing:-.45px; color:#172c46; line-height:1.1; }
.pp-sub { color:#5d7286; font-size:11.5px; margin-top:3px; }
.st-key-nav [role="radiogroup"] { gap: 6px; flex-wrap: wrap; }
.st-key-nav [role="radiogroup"] label { padding: 8px 14px; border-radius: 10px; margin: 0; cursor: pointer; }
.st-key-nav [data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) { display:none !important; }
.st-key-nav [data-testid="stRadioOption"] p { font-size:14px; font-weight:650; color:#5d7286; }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] { background:#eef4fa; box-shadow: inset 0 -3px 0 #2d78a8; }
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p { color:#1b456d; font-weight:750; }
.st-key-nav [data-testid="stRadioOption"]:focus-within { outline: 2px solid #5c9ac0; outline-offset: 2px; }
.pp-status { display:flex; justify-content:flex-end; align-items:center; gap:12px; min-height:46px; color:#5d7286; font-size:12.5px; }
.pp-dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; background:#36a28d; }
.pp-dot.err { background:#c2410c; }
.pp-avatar { width:32px; height:32px; border-radius:50%; background:#edf2f7; display:grid; place-items:center; color:#60758b; font-size:11px; font-weight:750; }

/* 소개 */
.pp-intro { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; flex-wrap:wrap; margin-top:6px; }
.pp-eyebrow { color:#68839a; font-size:11px; font-weight:800; letter-spacing:1.6px; margin-bottom:6px; }
.pp-h1 { margin:0; font-size:26px; line-height:1.25; letter-spacing:-.9px; font-weight:780; color:var(--ink); }
.pp-desc { font-size:14px; color:var(--muted); margin-top:6px; }
.pp-flag { display:flex; align-items:center; gap:6px; padding:8px 12px; border:1px solid #dfe8ef; border-radius:9px;
  background:#fbfdff; color:#596f84; font-size:12.5px; }

/* 패널 공통 */
.st-key-input_panel, .st-key-ko_panel, .st-key-ev_abbr, .st-key-ev_rule, .st-key-steps_panel, .st-key-rule_panel {
  background: var(--surface); border:1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px 16px; }
.st-key-input_panel { border-left: 3px solid #4f86ad; }
.pp-panel { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); }
.pp-input-copy { display:flex; gap:12px; align-items:center; }
.pp-lead { width:32px; height:32px; border-radius:9px; background:#eef4f8; color:#53738d; display:grid; place-items:center; flex:none; }
.pp-field-label { color:#354a61; font-weight:750; font-size:14px; }
.pp-field-hint { color:#607489; font-size:12px; margin-top:2px; }
.pp-privacy { display:flex; gap:8px; align-items:flex-start; color:#5d7285; font-size:12px; line-height:1.55; border-left:1px solid var(--line); padding-left:14px; }
[data-testid="stBaseButton-primary"] { background: var(--navy) !important; border-color: var(--navy) !important; border-radius:10px !important; font-weight:700 !important; min-height:44px; }
[data-testid="stBaseButton-secondary"] { border-radius:9px !important; border-color:#dce5ed !important; color:#536b82 !important; font-weight:650 !important; }
.stTextInput input, .stTextArea textarea { border-radius:10px !important; background:#fcfdff !important; }

/* 섹션 머리 */
.pp-sec { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-top:10px; }
.pp-sec-title { display:flex; align-items:center; gap:9px; font-size:17px; font-weight:780; letter-spacing:-.3px; color:var(--ink); }
.pp-sec-num { width:24px; height:24px; display:grid; place-items:center; border-radius:7px; background:#edf3f8; color:#54738d; font-size:11px; font-weight:800; }
.pp-sec-note { color:#60758a; font-size:12px; }

/* 3줄 뼈대 */
.pp-card { position:relative; overflow:hidden; padding:15px 17px 14px 19px; min-height:150px; height:100%; }
.pp-card:before { content:""; position:absolute; top:0; left:0; bottom:0; width:3px; background:#6c9dbb; }
.pp-card.teal:before { background:#3a9c92; } .pp-card.violet:before { background:#8b79b5; }
.pp-card-head { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:9px; }
.pp-kind { display:flex; align-items:center; gap:7px; font-size:13px; font-weight:780; color:#36536d; }
.pp-kdot { width:8px; height:8px; border-radius:50%; background:#6c9dbb; }
.teal .pp-kdot { background:#3a9c92; } .violet .pp-kdot { background:#8b79b5; }
.pp-basis { color:#60758a; font-size:11.5px; white-space:nowrap; }
.pp-basis.position { color:#9a681d; } .pp-basis.none { color:#8b98a9; }
.pp-sk-text { font-size:14px; color:#40536a; line-height:1.65; letter-spacing:-.1px; }
.pp-sk-no { color:#8090a1; font-size:11.5px; font-weight:750; margin-right:6px; }
.pp-sk-missing { font-size:14px; color:#8b98a9; }
.pp-sig-blue { background:#e7f1fb; color:#205d8b; font-weight:750; border-radius:4px; padding:1px 3px; }
.pp-sig-teal { background:#e5f5f1; color:#18796f; font-weight:750; border-radius:4px; padding:1px 3px; }
.pp-sig-violet { background:#f0ebf8; color:#7456a2; font-weight:750; border-radius:4px; padding:1px 3px; }
.pp-sk-ko { margin-top:8px; padding-top:8px; border-top:1px dashed #e3e9f0; font-size:13.5px; color:#4a5e73; line-height:1.65; }
.pp-u { text-decoration-line: underline; text-decoration-thickness: 2px; text-underline-offset: 4px; text-decoration-color:#6c9dbb; }
.pp-u.method { text-decoration-color:#3a9c92; } .pp-u.result { text-decoration-color:#8b79b5; }
.pp-u.def { text-decoration-style: dotted; text-decoration-thickness: 2px; text-decoration-color:#286b9c; }
.pp-u .pp-u.def { text-decoration: none; color:#205f90; }   /* 핵심 내용 밑줄 안의 용어 설명은 글자색으로만 */
.pp-u .pp-m, .pp-u [class^="pp-sig-"] { background: transparent !important; border-bottom: 0 !important; padding: 0; }
.pp-reason { display:flex; align-items:flex-start; gap:6px; margin-top:10px; color:#5c7084; font-size:12px; line-height:1.5; }
.pp-limit { color:#60758a; font-size:12px; margin-top:2px; }

/* 칩 */
.pp-chips { display:flex; gap:7px; flex-wrap:wrap; justify-content:flex-end; align-items:center; min-height:38px; }
.pp-chip { height:28px; padding:0 10px; border-radius:7px; display:inline-flex; align-items:center; font-size:12px; font-weight:750; }
.pp-chip.blue { color:#25618b; background:var(--blue-soft); } .pp-chip.amber { color:#986314; background:var(--amber-soft); }
.pp-chip.teal { color:#1f7b73; background:var(--teal-soft); } .pp-chip.violet { color:#73539d; background:var(--violet-soft); }

/* 원문·번역 */
.pp-reader-head { padding:12px 16px; border-bottom:1px solid #edf0f4; display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }
.pp-reader-title { display:flex; align-items:center; gap:8px; font-size:14px; font-weight:780; color:var(--ink); }
.pp-lang { background:#eff4f8; border-radius:5px; color:#60758b; padding:4px 7px; font-size:10.5px; font-weight:800; letter-spacing:.35px; }
.pp-meta { color:#60758a; font-size:12px; }
.pp-sents { padding:8px 16px 10px; }
.pp-sent { display:grid; grid-template-columns:24px 1fr; gap:10px; padding:9px 0; border-bottom:1px solid #f0f3f6; }
.pp-sent:last-child { border-bottom:0; }
.pp-no { width:22px; height:22px; border-radius:6px; background:#f1f5f8; color:#8090a1; display:grid; place-items:center; font-size:11px; font-weight:750; margin-top:1px; }
.pp-text { color:#34485f; font-size:14.5px; line-height:1.7; letter-spacing:-.1px; }
.pp-ko .pp-text { color:#4a5e73; font-size:14px; }
.pp-off { color:#9a681d; font-size:12.5px; margin-top:4px; }
.pp-m { position:relative; padding:0 2px; border-radius:3px; font-weight:700; cursor:help; }
.pp-m:focus { outline:2px solid #5c9ac0; outline-offset:1px; }
.pp-m.abbr { color:#205f90; background:#eaf3fb; border-bottom:1px solid #7ca9ca; }
.pp-m.abbr-missing { color:#52677f; background:#f1f4f7; border-bottom:1px dashed #9aa8b6; }
.pp-m.hedge { color:#956314; background:#fff4dd; border-bottom:1px solid #d7ac57; }
.pp-m.confident { color:#1c756d; background:#e8f5f1; }
.pp-m.reference { color:#73539d; background:#f0ebf8; }
/* 색은 늘리지 않는다: 용어 설명은 약어와 같은 파랑, 수치 근거는 확신과 같은 청록, 반복 용어는 파랑 얇은 밑줄 */
.pp-m.definition { color:#205f90; background:#eaf3fb; border-bottom:1px solid #7ca9ca; }
.pp-m.number { color:#1c756d; background:#e8f5f1; }
.pp-m.term { color:inherit; font-weight:650; background:transparent; padding:0; border-bottom:1.5px solid #7ca9ca; border-radius:0; }
.pp-m:hover::after, .pp-m:focus::after { content: attr(data-tip); position:absolute; left:0; top:calc(100% + 6px); z-index:20;
  background:#17293f; color:#fff; font-size:12px; font-weight:500; line-height:1.45; padding:7px 9px; border-radius:7px;
  width:max-content; max-width:300px; white-space:normal; box-shadow:0 6px 16px rgba(0,0,0,.18); }
.pp-banner { margin:-14px -16px 10px; padding:9px 16px; background:#f3f8fb; color:#536f86; font-size:12px; border-bottom:1px solid #edf0f4; }
.pp-notice { color:#52677f; font-size:13px; line-height:1.6; background:#fbfdff; border:1px dashed #d6e1ea; border-radius:10px; padding:12px 14px; margin-bottom:10px; }

/* 하단 근거 */
.pp-mini { display:flex; gap:12px; align-items:flex-start; }
.pp-mini-icon { flex:none; width:32px; height:32px; border-radius:9px; background:#f0f4f8; color:#59758d; display:grid; place-items:center; }
.pp-mini-title { display:flex; flex-wrap:wrap; align-items:center; gap:7px; font-size:13.5px; color:#3b5168; font-weight:780; margin-bottom:4px; }
.pp-mini-desc { color:#5c7084; font-size:12.5px; line-height:1.5; }
.pp-snip { color:#678096; font-family:ui-monospace, Consolas, monospace; font-size:11.5px; background:#f5f8fa; padding:3px 6px; border-radius:5px; }
.pp-foot { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:6px 2px 0; color:#60758a; font-size:12px; }
.pp-foot strong { color:#52697f; }

/* 이해를 돕는 자료: 흐름도 */
.pp-sub-title { font-size:14px; font-weight:780; color:#2c4560; margin:6px 0 6px; }
.pp-flow { display:flex; gap:6px; align-items:stretch; flex-wrap:wrap; }
.pp-flow-step { flex:1 1 170px; background:var(--surface); border:1px solid var(--line); border-top:3px solid #9aa8b6;
  border-radius:12px; padding:10px 12px; box-shadow:var(--shadow); }
.pp-flow-step.blue { border-top-color:#6c9dbb; } .pp-flow-step.teal { border-top-color:#3a9c92; }
.pp-flow-step.violet { border-top-color:#8b79b5; }
.pp-flow-head { display:flex; align-items:center; gap:5px; font-size:13px; color:#2c4560; margin-bottom:6px; }
.pp-flow-no { font-size:10.5px; font-weight:750; color:#60758a; background:#f1f5f8; border-radius:5px; padding:1px 5px; }
.pp-flow-text { font-size:13px; color:#34485f; line-height:1.55; }
.pp-flow-ko { font-size:12px; color:#5c7084; margin-top:5px; line-height:1.5; }
.pp-flow-arrow { align-self:center; color:#9aa8b6; font-size:18px; font-weight:700; }
.pp-flow-note { color:#60758a; font-size:12px; margin-top:6px; }
@media (max-width: 900px) { .pp-flow-arrow { display:none; } }

.pp-gloss th, .pp-gloss td:nth-child(-n+5) { white-space: nowrap; }
.pp-gloss td:nth-child(6) { min-width: 180px; }

/* 단계 보기·규칙 */
.pp-steps { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; }
.pp-step { border:1px solid #e8eef4; border-radius:10px; padding:10px; background:#fbfdff; }
.pp-step b { display:block; font-size:12.5px; color:#2c4560; margin-bottom:4px; }
.pp-step span { font-size:12px; color:#5c7084; line-height:1.45; }
.pp-table { width:100%; border-collapse:collapse; font-size:13.5px; }
.pp-table th { text-align:left; color:#52677f; font-weight:700; padding:9px 10px; border-bottom:1px solid var(--line); background:#f8fafc; }
.pp-table td { padding:10px; border-bottom:1px solid #eef2f6; vertical-align:top; color:#34485f; line-height:1.55; }
.pp-tag { display:inline-block; padding:2px 8px; border-radius:6px; font-size:11.5px; font-weight:750; }
.pp-tag.measured { background:var(--teal-soft); color:#1f7b73; } .pp-tag.target { background:var(--amber-soft); color:#986314; }
.pp-tag.planned { background:#eef2f6; color:#52677f; }

@media (max-width: 900px) {
  .pp-steps { grid-template-columns:repeat(2,1fr); }
  .pp-privacy { border-left:0; padding-left:0; }
  .pp-h1 { font-size:23px; }
}
</style>
"""


# ================================================================ 상태

def init_state() -> None:
    ss = st.session_state
    ss.setdefault("page", PAGES[0])
    ss.setdefault("input_mode", MODES[0])
    ss.setdefault("arxiv_id", "")
    ss.setdefault("paste_text", "")
    ss.setdefault("input_text", DEMO_TEXT)
    ss.setdefault("source", {"kind": "demo"})
    ss.setdefault("active_rules", set(P.DEFAULT_ACTIVE_RULES))
    ss.setdefault("translations", {})
    ss.setdefault("show_steps", False)
    ss.setdefault("show_translation", True)
    ss.setdefault("input_error", None)
    ss.setdefault("deepl_calls", 0)


@st.cache_resource
def engine_ok() -> bool:
    try:
        return analyze("We introduce a method (ABC) that may work [1].").sentences != []
    except Exception:
        return False


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def go_page(name: str) -> None:
    st.session_state.page = name


def load_demo() -> None:
    st.session_state.input_text = DEMO_TEXT
    st.session_state.source = {"kind": "demo"}
    st.session_state.input_error = None


def seed_rule_widgets() -> None:
    """규칙 체크박스는 패널이 닫히면 위젯 상태가 지워지므로, 매번 active_rules에서 다시 채운다."""
    for r in P.TOGGLEABLE_RULES:
        st.session_state.setdefault(f"rule_{r.name}", r.name in st.session_state.active_rules)


def on_rule_change(name: str) -> None:
    rules = set(st.session_state.active_rules)
    (rules.add if st.session_state[f"rule_{name}"] else rules.discard)(name)
    st.session_state.active_rules = rules


def rule_toggles(container_cols: int = 3) -> None:
    seed_rule_widgets()
    cols = st.columns(container_cols)
    for i, r in enumerate(P.TOGGLEABLE_RULES):
        with cols[i % container_cols]:
            st.checkbox(f"{r.label} ({r.name})", key=f"rule_{r.name}", on_change=on_rule_change, args=(r.name,),
                        help=r.desc)


# ================================================================ 렌더링 도우미

def esc(s: str) -> str:
    return html.escape(s, quote=True)


def as_wrappers(u) -> list:
    """밑줄 값(하나, 목록, None)을 목록으로 맞춘다."""
    if not u:
        return []
    return [u] if isinstance(u[0], int) else list(u)


def render_layers(text: str, spans, underline=None) -> str:
    """형광펜(spans)과 밑줄(underline: 핵심 내용·용어 설명)을 함께 그린다.

    spans: [(시작, 끝, CSS 클래스, 툴팁)] — 서로 겹치지 않는다.
    underline: (시작, 끝, 종류[, 툴팁]) 하나 또는 목록. 앞의 것이 우선이고 겹치는 뒤의 것은 버린다.
    형광펜을 자르지 않도록 밑줄 경계를 넓힌다. 밑줄 안의 형광펜은 CSS에서 배경을 빼고 글자색만 남긴다.
    """
    spans = sorted(sp for sp in spans if 0 <= sp[0] < sp[1] <= len(text))
    wraps = []
    for w in as_wrappers(underline):
        ua, ub, kind = w[0], w[1], w[2]
        if not (0 <= ua < ub <= len(text)):
            continue
        for a, b, *_ in spans:
            if a < ua < b:
                ua = a
            if a < ub < b:
                ub = b
        # 겹치지 않으면 그대로, 용어 설명이 핵심 내용 밑줄 안에 통째로 들어가면 안쪽에 겹쳐 그린다(교차하면 버림)
        inside = [o for o in wraps if o[0] <= ua and ub <= o[1]]
        crossing = [o for o in wraps if not (ub <= o[0] or ua >= o[1]) and o not in inside]
        if crossing or (inside and kind != "def"):
            continue
        wraps.append((ua, ub, kind, w[3] if len(w) > 3 else UL_TITLE.get(kind, "")))
    cuts = sorted({0, len(text), *(e for sp in spans for e in sp[:2]), *(e for w in wraps for e in w[:2])})
    out = []
    for x, y in zip(cuts, cuts[1:]):
        for w in sorted((w for w in wraps if w[0] == x), key=lambda w: -(w[1] - w[0])):   # 바깥 밑줄부터 연다
            out.append(f'<span class="pp-u {w[2]}" title="{esc(w[3])}">')
        sp = next((sp for sp in spans if sp[0] == x and sp[1] == y), None)
        if sp:
            tip = esc(sp[3])
            out.append(f'<span class="{sp[2]}" tabindex="0" title="{tip}" data-tip="{tip}" aria-label="{tip}">'
                       f'{esc(text[x:y])}</span>')
        else:
            out.append(esc(text[x:y]))
        out.extend("</span>" for w in wraps if w[1] == y)
    return "".join(out)


def render_ko(ko: str, ko_marks, active, underline=None) -> str:
    """번역문 형광펜·밑줄. 위치는 DeepL이 옮긴 태그에서 복원한 것이라 툴팁에 '대응 추정'임을 밝힌다."""
    spans, last = [], -1
    for a, b, cat, en in ko_marks:
        if CAT_RULE.get(cat) in active and a >= last:
            spans.append((a, b, f"pp-m {cat}", f"{MARK_LABEL[cat]} · 영어 '{en}'에 대응 (번역기가 옮긴 위치)"))
            last = b
    return render_layers(ko, spans, underline)


def card_underlines(a) -> dict[int, list]:
    """문장 번호 → 그 문장의 밑줄 목록(문장 안 위치). 핵심 내용(신호 문구로 찾은 카드)이 먼저, 용어 설명이 뒤."""
    out: dict[int, list] = {}
    for c in a.skeleton:
        if c.sentence_idx is not None and c.underline:
            out.setdefault(c.sentence_idx, []).append((*c.underline, c.kind))
    for x, y, tip in a.explanations:
        s = next((s for s in a.sentences if s.start <= x < s.end), None)
        if s:
            out.setdefault(s.idx, []).append((x - s.start, min(y, s.end) - s.start, "def", tip))
    return out


def translation_layers(raw_text: str):
    """번역에 보낼 문장별 영어 형광펜·밑줄. 규칙 켜고 끄기와 상관없이 기본 규칙으로 만들어 캐시를 안정시킨다."""
    full = analyze(raw_text)
    uls = card_underlines(full)
    marks = [[(m.start - s.start, m.end - s.start, m.category) for m in full.marks if s.start <= m.start and m.end <= s.end]
             for s in full.sentences]
    jargon = G.jargon_marks(full)   # 단어표의 한국어 대응어를 얻으려는 태그(화면에는 그리지 않음)
    for s, row in zip(full.sentences, marks):
        row += [(x - s.start, y - s.start, c) for x, y, c in jargon if s.start <= x and y <= s.end
                and all(y - s.start <= a or x - s.start >= b for a, b, _ in row)]
    return marks, [[w[:3] for w in uls.get(s.idx, [])] for s in full.sentences]


def render_marked(text: str, start: int, end: int, marks, underline=None) -> str:
    """원문 문장(text[start:end]) 렌더링. underline은 문장 안 위치."""
    spans = [(max(m.start, start) - start, min(m.end, end) - start, f"pp-m {m.category}",
              f"{MARK_LABEL[m.category]} · {m.tip}") for m in marks if m.end > start and m.start < end]
    return render_layers(text[start:end], spans, underline)


def skeleton_card(card, a, ko: str | None = None, ko_ul=None) -> str:
    title, color = KIND_META[card.kind]
    basis_cls = card.basis
    basis_tip = {"signal": "신호 문구로 찾은 문장이에요. 밑줄은 신호 문구가 가리키는 핵심 내용이에요.",
                 "position": "신호 문구가 없어 위치로 고른 추정 문장이에요. 근거가 없어 핵심 내용 밑줄은 긋지 않아요.",
                 "none": "규칙에 맞는 문장을 찾지 못했어요."}[card.basis]
    if card.sentence_idx is None:
        body = f'<div class="pp-sk-missing">{esc(card.label)}</div>'
        basis = BASIS_TEXT["none"]
    else:
        s = a.sentences[card.sentence_idx].text
        spans = [(*card.signal, f"pp-sig-{color}", f"신호 문구 · {card.reason}")] if card.signal else []
        ul = card_underlines(a).get(card.sentence_idx, [])
        body = (f'<div class="pp-sk-text"><span class="pp-sk-no">문장 {card.sentence_idx + 1}</span>'
                f'{render_layers(s, spans, ul)}</div>')
        if ko:
            body += f'<div class="pp-sk-ko">{render_layers(ko, [], ko_ul)}</div>'
        basis = card.label
    return (f'<div class="pp-panel pp-card {color}"><div class="pp-card-head"><div class="pp-kind">'
            f'<span class="pp-kdot"></span>{title}</div><div class="pp-basis {basis_cls}" title="{esc(basis_tip)}">'
            f'{esc(basis)}</div></div>'
            f'{body}<div class="pp-reason">{ICON["info"]}<span>{esc(card.reason)}</span></div></div>')


ROLE_META = {"background": ("배경", "gray"), "problem": ("문제", "blue"), "method": ("방법", "teal"),
             "result": ("결과", "violet"), "limit": ("한계", "gray")}


def flow_map(a, tr=None) -> str:
    """논문 흐름도: 문장 역할(배경 → 문제 → 방법 → 결과 → 한계)을 순서대로 이어 보여 준다."""
    uls = {c.sentence_idx: c.underline for c in a.skeleton if c.sentence_idx is not None and c.underline}
    steps = []
    for role in ROLE_ORDER:
        idxs = [i for i, r in enumerate(a.roles) if r == role]
        if not idxs:
            continue
        name, color = ROLE_META[role]
        i = idxs[0]
        s = a.sentences[i].text
        if i in uls:
            snippet = s[uls[i][0]:uls[i][1]]
        else:
            words = s.split()
            snippet = " ".join(words[:14]) + (" …" if len(words) > 14 else "")
        ko = ""
        if tr and tr.ko and i < len(tr.ko):
            k = tr.ko[i]
            ko = f'<div class="pp-flow-ko">{esc(k[:60] + ("…" if len(k) > 60 else ""))}</div>'
        nums = "".join(f'<span class="pp-flow-no">{j + 1}</span>' for j in idxs)
        steps.append(f'<div class="pp-flow-step {color}"><div class="pp-flow-head"><b>{name}</b>{nums}</div>'
                     f'<div class="pp-flow-text">{esc(snippet)}</div>{ko}</div>')
    if not steps:
        return '<div class="pp-meta">문장이 없어요.</div>'
    detail = [i + 1 for i, r in enumerate(a.roles) if r == "detail"]
    note = (f'<div class="pp-flow-note">보충 문장: {", ".join(f"문장 {j}" for j in detail)} '
            f'(신호 문구가 없어 흐름 단계로 분류하지 않았어요)</div>') if detail else ""
    arrow = '<div class="pp-flow-arrow" aria-hidden="true">→</div>'
    return f'<div class="pp-flow">{arrow.join(steps)}</div>{note}'


def glossary_table(rows) -> str:
    if not rows:
        return '<div class="pp-meta">이 글에서 어려운 단어(전문용어)를 찾지 못했어요.</div>'
    body = "".join(
        f"<tr><td><b>{esc(e.term)}</b></td><td>{esc(', '.join(G.KIND_LABEL[k] for k in e.kinds))}</td>"
        f"<td>{esc(e.level) or '-'}</td>"
        f"<td>{e.count}</td><td>{('문장 ' + str(e.first_sentence)) if e.first_sentence else '-'}</td>"
        f"<td>{esc(e.explanation) or '-'}</td><td>{esc(e.korean) or '-'}</td></tr>" for e in rows)
    return (f'<div class="pp-panel" style="padding:6px 8px; overflow-x:auto"><table class="pp-table pp-gloss"><thead><tr>'
            f'<th>용어</th><th>종류</th><th>난이도</th><th>횟수</th><th>처음 나온 곳</th><th>풀네임·설명(원문)</th><th>한국어</th>'
            f'</tr></thead><tbody>{body}</tbody></table></div>')


def sec_head(num: str, title: str, note: str = "") -> str:
    return (f'<div class="pp-sec"><div class="pp-sec-title"><span class="pp-sec-num">{num}</span>{esc(title)}</div>'
            f'<div class="pp-sec-note">{esc(note)}</div></div>')


# ================================================================ 상단 바·소개

def topbar() -> None:
    ok = engine_ok()
    with st.container(key="topbar"):
        c1, c2, c3 = st.columns([1.25, 2.1, 1.25], vertical_alignment="center")
        c1.markdown(f'<div class="pp-brand"><div class="pp-mark">{ICON["doc"]}</div><div>'
                    f'<div class="pp-name">PaperPath</div><div class="pp-sub">처음 읽는 영어 논문 도우미</div></div></div>',
                    unsafe_allow_html=True)
        with c2, st.container(key="nav"):
            st.radio("페이지", PAGES, key="page", horizontal=True, label_visibility="collapsed")
        status = ('<span class="pp-dot"></span>규칙 엔진 준비됨' if ok
                  else '<span class="pp-dot err"></span>규칙 엔진 오류')
        c3.markdown(f'<div class="pp-status"><span role="status">{status}</span>'
                    f'<span class="pp-avatar" aria-hidden="true">PP</span></div>', unsafe_allow_html=True)


def source_flag() -> str:
    src = st.session_state.source
    if src["kind"] == "demo":
        return "화면 예시 데이터 · 직접 작성, 실제 논문 아님"
    if src["kind"] == "arxiv":
        return f"arXiv {src['id']} · {src.get('title', '')[:40]} · 메타데이터 CC0"
    return "붙여 넣은 텍스트 · 앱에 저장하지 않음"


# ================================================================ 논문 읽기

def input_panel() -> None:
    ss = st.session_state
    with st.container(key="input_panel"):
        c1, c2, c3, c4, c5 = st.columns([1.6, 1.75, 2.1, 1.25, 2.3], vertical_alignment="center")
        c1.markdown(f'<div class="pp-input-copy"><div class="pp-lead">{ICON["search"]}</div><div>'
                    f'<div class="pp-field-label">분석할 논문 불러오기</div>'
                    f'<div class="pp-field-hint">arXiv ID 또는 직접 붙여 넣기</div></div></div>', unsafe_allow_html=True)
        with c2:
            mode = st.segmented_control("입력 방식", MODES, key="input_mode", label_visibility="collapsed") or MODES[0]
        with c3:
            if mode == MODES[0]:
                st.text_input("arXiv ID", key="arxiv_id", placeholder="arXiv ID  예: 2402.08910",
                              label_visibility="collapsed")
            else:
                st.caption("아래 칸에 영어 초록이나 단락을 붙여 넣으세요.")
        with c4:
            clicked = st.button("초록 불러오기" if mode == MODES[0] else "분석하기", type="primary",
                                use_container_width=True, key="load_btn")
        c5.markdown(f'<div class="pp-privacy">{ICON["shield"]}<span>붙여 넣은 텍스트는 저장하지 않아요.<br>'
                    f'번역 시 {engine_name()}로 전송됨을 미리 안내합니다.</span></div>', unsafe_allow_html=True)
        if mode == MODES[1]:
            st.text_area("영어 텍스트", key="paste_text", height=150, label_visibility="collapsed",
                         placeholder="영어 논문 초록이나 단락을 붙여 넣으세요. PDF 복사 잔재(줄바꿈·쪽번호·머리말)는 자동으로 정리해요.")
        st.button("예시 문단으로 보기", key="demo_btn", type="tertiary", on_click=load_demo)

        if clicked:
            ss.input_error = None
            if mode == MODES[0]:
                with st.spinner("arXiv에서 초록을 불러오는 중…"):
                    try:
                        row = fetch_abstract(ss.arxiv_id)
                        ss.input_text = row["abstract"]
                        ss.source = {"kind": "arxiv", "id": row["id"], "title": row["title"]}
                    except ArxivError as e:
                        ss.input_error = str(e)
            else:
                txt = ss.paste_text.strip()
                letters = sum(ch.isalpha() for ch in txt)
                if not txt:
                    ss.input_error = "붙여 넣은 텍스트가 없어요."
                elif len(txt) > MAX_PASTE:
                    ss.input_error = f"텍스트가 너무 길어요({len(txt):,}자). {MAX_PASTE:,}자 이하로 나눠 넣어 주세요."
                elif letters and sum(ch.isascii() for ch in txt if ch.isalpha()) / letters < 0.8:
                    ss.input_error = "영어 텍스트가 아닌 것 같아요. 영어 초록이나 단락을 넣어 주세요."
                else:
                    ss.input_text = txt
                    ss.source = {"kind": "paste"}
        if ss.input_error:
            st.error(ss.input_error)


def steps_panel(a) -> None:
    with st.container(key="steps_panel"):
        n_def = sum(1 for v in a.acronyms.values() if v)
        picks = ", ".join(f"{KIND_META[c.kind][0].split(' ·')[0]}={'문장 ' + str(c.sentence_idx + 1) if c.sentence_idx is not None else '없음'}"
                          for c in a.skeleton)
        steps = [
            ("① 전처리", f"최소 방어선 5종 적용. 지운 줄 {len(a.removed_lines)}개"),
            ("② 문장 분리", f"{len(a.sentences)}문장. 수식·인용·URL 안 마침표는 가림"),
            ("③ 약어 탐지", f"후보 {len(a.acronyms)}개, 풀네임 {n_def}개"),
            ("④ 뼈대 선택", picks),
            ("⑤ 추측·확신·참조", f"추측 {a.counts['hedge']} · 확신 {a.counts['confident']} · 참조 {a.counts['reference']}"),
            ("⑥ 번역(선택)", "버튼을 눌렀을 때만 번역 API 호출(Claude Haiku 또는 DeepL)"),
        ]
        st.markdown('<div class="pp-steps">' + "".join(f'<div class="pp-step"><b>{esc(t)}</b><span>{esc(d)}</span></div>'
                                                        for t, d in steps) + "</div>", unsafe_allow_html=True)
        if a.removed_lines:
            st.caption("제거된 줄: " + " / ".join(a.removed_lines[:8]))
        st.markdown("**준비된 규칙 켜고 끄기** · 끄면 위 원문 표시가 바로 바뀌어요(자유 정규식 입력은 없음)")
        rule_toggles()


def secret(name: str) -> str | None:
    """배포 사이트는 Streamlit 비밀값(st.secrets), 로컬은 .env에서 키를 읽는다. 키 값은 화면·로그에 내보내지 않는다."""
    try:
        key = st.secrets.get(name)
    except Exception:          # 로컬에 secrets.toml이 없으면 예외가 난다
        key = None
    return key or T.load_api_key(name)


def engine():
    """번역 엔진: Claude 키가 있으면 Claude Haiku 5.5, 없으면 DeepL."""
    return T.pick_engine(secret("ANTHROPIC_API_KEY"), secret("DEEPL_API_KEY"))


def engine_name() -> str:
    return "Claude(Anthropic) API" if engine()[0] == "claude" else "DeepL API"


def limited_caller(texts: list[str], key: str, split: str) -> list[str]:
    """실제로 번역 API를 부르는 순간에만 사용 제한을 확인하고 센다(캐시에서 답하면 세지 않음)."""
    ss = st.session_state
    chars = sum(len(T.unprotect(t)) for t in texts)
    reason = usage.check(chars, ss.deepl_calls)
    if reason:
        raise T.TranslationError(reason)
    out = engine()[2](texts, key, split)
    usage.record(chars)
    ss.deepl_calls += 1            # 엔진과 상관없이 이 화면의 번역 호출 수
    return out


def run_translate(sents, a, masked: bool, file_cache: bool, **layers):
    name, key, _ = engine()
    return T.translate(sents, a.acronyms, masked=masked, use_file_cache=file_cache, api_key=key,
                       caller=limited_caller, engine=name, **layers)


def translation_panel(a) -> None:
    ss = st.session_state
    sents = [s.text for s in a.sentences]
    tkey = text_key(a.text)
    file_cache = ss.source["kind"] in ("demo", "arxiv")   # 붙여 넣은 텍스트의 번역은 파일에 남기지 않는다
    with st.container(key="ko_panel"):
        h1, h2 = st.columns([3, 1.3], vertical_alignment="center")
        h1.markdown('<div class="pp-reader-title"><span class="pp-lang">KO</span>한국어 번역 '
                    '<span class="pp-meta">· 문장별 대응</span></div>', unsafe_allow_html=True)
        with h2:
            on = st.toggle("번역 켜짐", key="show_translation")
        if not on:
            st.markdown('<div class="pp-notice">번역을 껐어요. 원문 표시와 3줄 뼈대는 그대로 동작해요.</div>',
                        unsafe_allow_html=True)
            return

        res = ss.translations.get((tkey, True))
        if res is None:
            st.markdown(f'<div class="pp-notice"><b>번역하기</b>를 누르면 위 영어 문장이 <b>{engine_name()}로 전송</b>돼요. '
                        '이 앱은 입력을 저장하지 않지만, 번역 서비스 측의 보관 정책은 그 서비스의 약관을 따라요. '
                        '개인정보는 넣지 마세요.</div>', unsafe_allow_html=True)
            if st.button("번역하기", type="primary", key="translate_btn"):
                with st.spinner("번역하는 중…"):
                    ss.translations[(tkey, True)] = run_translate(
                        sents, a, True, file_cache, **dict(zip(("marks", "underlines"), translation_layers(ss.input_text))))
                st.rerun()
            return

        if res.error and res.ko is None and res.paragraph is None:
            st.warning(res.error)
            if st.button("다시 시도", key="retry_btn"):
                ss.translations.pop((tkey, True), None)
                st.rerun()
            return

        mode_note = {"aligned": "원문 문장과 1:1 연결 · 문단 + 문장 태그", "per_sentence": "원문 문장과 1:1 연결 · 문장별 전송",
                     "paragraph": "문장 수가 맞지 않아 문단 단위로 보여 줘요"}[res.mode]
        st.markdown(f'<div class="pp-meta">{esc(mode_note)}{" · 저장된 번역" if res.cached else ""} · '
                    f'{esc(T.ENGINE_LABEL[engine()[0]])}</div>',
                    unsafe_allow_html=True)
        off = ss.translations.get((tkey, False))
        if res.ko is not None:
            marks_ko = res.ko_marks or []
            uls_ko = res.ko_underlines or []
            rows = []
            for i, ko in enumerate(res.ko):
                extra = ""
                if off and off.ko is not None and i < len(off.ko) and off.ko[i] != ko:
                    extra = f'<div class="pp-off">마스킹 끔: {esc(off.ko[i])}</div>'
                rows.append(f'<div class="pp-sent pp-ko"><div class="pp-no">{i + 1:02d}</div>'
                            f'<div><div class="pp-text">{render_ko(ko, marks_ko[i] if i < len(marks_ko) else [], a.active_rules, as_wrappers(uls_ko[i]) if i < len(uls_ko) else None)}</div>{extra}</div></div>')
            st.markdown(f'<div class="pp-sents" style="padding:0">{"".join(rows)}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="pp-text">{esc(res.paragraph or "")}</div>', unsafe_allow_html=True)

        if off is None:
            if st.button("마스킹 끔과 비교", key="compare_btn", help="보호 마스킹 없이 한 번 더 번역해 차이를 보여 줘요(번역 API 추가 호출)"):
                with st.spinner("마스킹 없이 번역하는 중…"):
                    ss.translations[(tkey, False)] = run_translate(sents, a, False, file_cache)
                st.rerun()
        elif off.ko is None:
            st.warning(off.error or "비교 번역을 만들지 못했어요.")
        elif res.ko is not None:
            toks = [(t, i) for i, ts in enumerate(res.protected) for t in ts]
            lost_off = [t for t, i in toks if i < len(off.ko) and t not in off.ko[i]]
            diff = sum(1 for x, y in zip(res.ko, off.ko) if x != y)
            st.info(f"보호 토큰 {len(toks)}개 중 마스킹 끔에서 바뀐 것 {len(lost_off)}개"
                    f"{(' (' + ', '.join(lost_off[:5]) + ')') if lost_off else ''} · 번역이 달라진 문장 {diff}개. "
                    "차이가 작을 수 있어요(검증 결과 탭의 30편 실측 참고).")
        st.caption(f"번역 사용: 이 화면 {ss.deepl_calls}/{usage.MAX_CALLS_PER_SESSION}회 · "
                   f"오늘 사이트 전체 {usage.used_today():,}/{usage.DAILY_CHAR_CAP:,}자 · 한 번에 {usage.MAX_CHARS_PER_REQUEST:,}자까지")


def reading_page() -> None:
    ss = st.session_state
    st.markdown(f'<div class="pp-intro"><div><div class="pp-eyebrow">ACADEMIC READING WORKSPACE</div>'
                f'<h1 class="pp-h1">논문을 읽는 길을 먼저 보여드려요.</h1>'
                f'<div class="pp-desc">원문은 그대로, 핵심 문장과 읽기 신호는 한눈에.</div></div>'
                f'<div class="pp-flag">{ICON["info"]}{esc(source_flag())}</div></div>', unsafe_allow_html=True)
    input_panel()

    a = analyze(ss.input_text, frozenset(ss.active_rules))

    st.markdown(sec_head("01", "먼저 읽을 3줄 뼈대", "원문에서 찾은 문장 · 신호 문구와 선택 이유를 함께 표시"),
                unsafe_allow_html=True)
    cols = st.columns(3)
    tr = ss.translations.get((text_key(a.text), True))
    for col, card in zip(cols, a.skeleton):
        i = card.sentence_idx
        ko = tr.ko[i] if tr and tr.ko and i is not None and i < len(tr.ko) else None
        ko_ul = as_wrappers(tr.ko_underlines[i]) if ko and tr.ko_underlines and i < len(tr.ko_underlines) else None
        col.markdown(skeleton_card(card, a, ko, ko_ul), unsafe_allow_html=True)
    if a.limit_idx:
        st.markdown(f'<div class="pp-limit">한계·향후 과제 문장: {", ".join("문장 " + str(i + 1) for i in a.limit_idx)}</div>',
                    unsafe_allow_html=True)

    t1, t2, t3 = st.columns([1.4, 2.2, 1], vertical_alignment="center")
    t1.markdown(sec_head("02", "원문과 번역을 나란히 읽기"), unsafe_allow_html=True)
    c = a.counts
    t2.markdown(f'<div class="pp-chips"><span class="pp-chip blue">약어 {c["abbr"]}</span>'
                f'<span class="pp-chip amber">추측·가능성 {c["hedge"]}</span>'
                f'<span class="pp-chip teal">확신 {c["confident"]}</span>'
                f'<span class="pp-chip violet">참조 {c["reference"]}</span>'
                f'<span class="pp-chip blue">용어 설명 {c["definition"]}</span>'
                f'<span class="pp-chip blue">반복 용어 {c["term"]}</span>'
                f'<span class="pp-chip teal">수치 {c["number"]}</span></div>', unsafe_allow_html=True)
    with t3:
        st.toggle("읽기 전용 단계 보기", key="show_steps")
    if ss.show_steps:
        steps_panel(a)

    left, right = st.columns([1.13, 0.87])
    uls = card_underlines(a)
    with left:
        rows = "".join(f'<div class="pp-sent"><div class="pp-no">{s.idx + 1}</div>'
                       f'<div class="pp-text">{render_marked(a.text, s.start, s.end, a.marks, uls.get(s.idx))}</div></div>'
                       for s in a.sentences)
        st.markdown(f'<div class="pp-panel"><div class="pp-reader-head"><div class="pp-reader-title">'
                    f'<span class="pp-lang">EN</span>영어 원문 <span class="pp-meta">· {len(a.sentences)}문장</span></div>'
                    f'<div class="pp-meta">표현에 마우스를 올리거나 Tab으로 이동하면 정의와 규칙이 보여요</div></div>'
                    f'<div class="pp-sents">{rows or "<div class=pp-meta>문장이 없어요.</div>"}</div></div>',
                    unsafe_allow_html=True)
    with right:
        translation_panel(a)

    st.markdown(sec_head("03", "이해를 돕는 자료", "흐름도·단어표 — 정규식이 찾은 결과를 한눈에 모은 것"),
                unsafe_allow_html=True)
    tr = ss.translations.get((text_key(a.text), True))
    st.markdown('<div class="pp-sub-title">논문 흐름도</div>', unsafe_allow_html=True)
    st.markdown(flow_map(a, tr), unsafe_allow_html=True)
    rows = G.build(a, G.korean_marks(tr))
    g1, g2 = st.columns([4, 1], vertical_alignment="bottom")
    g1.markdown(f'<div class="pp-sub-title">어려운 단어표 · {len(rows)}개</div>', unsafe_allow_html=True)
    g2.download_button("단어표 내려받기(CSV)", G.to_csv(rows), file_name="paperpath_glossary.csv", mime="text/csv",
                       key="glossary_csv", disabled=not rows, use_container_width=True)
    st.markdown(glossary_table(rows), unsafe_allow_html=True)
    st.caption("일상 영어에서 드문 단어(전문용어)·약어·모델 이름만 모았어요. 난이도는 일상 영어 빈도 기준"
               "(wordfreq, Zipf 3.0 미만 '상', 3.0~3.5 '중'). 한국어는 '번역하기'를 누른 뒤 번역기가 옮긴 대응어라 참고용이에요.")

    b1, b2 = st.columns(2)
    defined = {k: v for k, v in a.acronyms.items() if v}
    first = next(iter(defined.items()), None)
    with b1, st.container(key="ev_abbr"):
        m1, m2 = st.columns([4, 1.1], vertical_alignment="center")
        snip = f'<span class="pp-snip">{esc(first[0])} → {esc(first[1])}</span>' if first else ""
        m1.markdown(f'<div class="pp-mini"><div class="pp-mini-icon">{ICON["list"]}</div><div>'
                    f'<div class="pp-mini-title">탐지된 약어 {len(a.acronyms)}개 {snip}</div>'
                    f'<div class="pp-mini-desc">괄호 안 약어 후보를 찾고, 앞 단어의 첫 글자를 맞춰 풀네임을 확인합니다.</div>'
                    f'</div></div>', unsafe_allow_html=True)
        with m2.popover("정의 확인", use_container_width=True):
            if a.acronyms:
                st.markdown("\n".join(f"- **{k}** → {v if v else '정의를 찾지 못함'}" for k, v in a.acronyms.items()))
            else:
                st.write("탐지된 약어가 없어요.")
    with b2, st.container(key="ev_rule"):
        m1, m2 = st.columns([4, 1.1], vertical_alignment="center")
        m1.markdown(f'<div class="pp-mini"><div class="pp-mini-icon">{ICON["rule"]}</div><div>'
                    f'<div class="pp-mini-title">규칙 근거 <span class="pp-snip">may / might / could</span></div>'
                    f'<div class="pp-mini-desc">추측·가능성 표현을 한 등급으로 표시하고, 가능·허용 의미는 제외합니다.</div>'
                    f'</div></div>', unsafe_allow_html=True)
        m2.button("규칙 보기", key="to_rules", on_click=go_page, args=("규칙 탐색",), use_container_width=True)

    st.markdown('<div class="pp-foot"><span><strong>읽는 길은 정규식이, 판단은 학생이.</strong> '
                '원문은 수정하거나 요약문으로 대체하지 않습니다.</span><span>번역은 버튼을 누를 때만 · 외부 서비스 전송 안내 포함</span></div>',
                unsafe_allow_html=True)


# ================================================================ 규칙 탐색

def rules_page() -> None:
    st.markdown('<div class="pp-intro"><div><div class="pp-eyebrow">RULE EXPLORER</div>'
                '<h1 class="pp-h1">화면의 모든 표시는 이 규칙에서 나와요.</h1>'
                '<div class="pp-desc">준비된 규칙만 켜고 끌 수 있어요. 임의의 정규식을 입력하는 기능은 없습니다.</div></div></div>',
                unsafe_allow_html=True)
    with st.container(key="rule_panel"):
        st.markdown("**처리 단계(읽기 전용)**")
        st.markdown('<div class="pp-steps">' + "".join(
            f'<div class="pp-step"><b>{t}</b><span>{d}</span></div>' for t, d in [
                ("① 전처리", "줄바꿈·공백·하이픈·쪽번호·반복 머리말"),
                ("② 문장 분리", "수식·인용·URL을 가린 뒤 마침표 경계"),
                ("③ 약어", "괄호 안 후보(regex) → 글자 맞추기(Python)"),
                ("④ 3줄 뼈대", "신호 문구 → 위치 대체(추정 표시)"),
                ("⑤ 추측·확신·참조", "단일 등급 + 가능·허용 제외"),
                ("⑥ 번역(선택)", "보호 마스킹 → Claude Haiku 또는 DeepL → 태그로 짝 복원"),
            ]) + "</div>", unsafe_allow_html=True)
        st.markdown("**규칙 켜고 끄기 미리보기**")
        rule_toggles()
        a = analyze(RULE_DEMO, frozenset(st.session_state.active_rules))
        s = a.sentences[0]
        st.markdown(f'<div class="pp-text" style="padding:8px 0">{render_marked(a.text, s.start, s.end, a.marks)}</div>',
                    unsafe_allow_html=True)
        st.caption("예: '추측 제외(가능·허용)'를 끄면 may be applied의 may가 추측으로 칠해져요.")

    st.markdown(sec_head("R", "준비된 규칙 목록", "patterns.py에서 그대로 가져온 내용"), unsafe_allow_html=True)
    for r in (*P.TOKEN_RULES, *P.SKELETON_RULES, P.POSITION_FALLBACK_RULE):
        with st.expander(f"{r.label} · {r.name}"):
            st.write(r.desc)
            if r.reason:
                st.caption(f"화면 이유 문구: {r.reason}")
            if r.examples:
                st.markdown("**잡는 예**: " + " / ".join(f"`{e}`" for e in r.examples))
            if r.misses:
                st.markdown("**일부러 놓치는 경우**: " + " / ".join(f"`{e}`" for e in r.misses))
            st.code(r.pattern.pattern, language="regex")


# ================================================================ 검증 결과

@st.cache_data(show_spinner=False)
def cached_skeleton_stats() -> dict:
    return skeleton_stats(load_samples())


def validation_page() -> None:
    st.markdown('<div class="pp-intro"><div><div class="pp-eyebrow">VALIDATION</div>'
                '<h1 class="pp-h1">측정한 것과 목표를 나눠서 보여 드려요.</h1>'
                '<div class="pp-desc">표본이 작아 일반화하지 않습니다. 측정 전인 항목은 목표나 예정으로 표시합니다.</div></div></div>',
                unsafe_allow_html=True)
    stats = cached_skeleton_stats()
    n = stats["n"]
    so, wf = stats["signal_only"], stats["with_fallback"]
    bench = load_benchmark()
    if bench:
        b = bench["summary"]
        mask_row = ("measured", f"{b['date']} · 초록 {b['papers']}편 · 보호 토큰 {b['tokens']}개 중 문자열 그대로 남은 것: "
                    f"마스킹 켬 {b['on_kept']}개 / 끔 {b['off_kept']}개. 단, 끔 쪽 차이 대부분은 값이 같은 표기 변환이었고 "
                    "의미 있는 손실은 약어 2건뿐. 켬 쪽에서는 수치 보호 때문에 틀린 숫자가 1건 나와 수치 보호를 뺐어요(아래 상세)")
    else:
        mask_row = ("planned", "2주차 실측 예정(30편). 사전 3문장 실험(2026-11-04)에서는 마스킹 끔에서도 BERT·3.1%·[4]가 "
                    "보존됐고 Table 1이 '표 1'로 바뀐 차이만 있었어요")
    rows = [
        ("3줄 뼈대 채움률 — 신호 문구만", "measured",
         f"arXiv cs.CL 초록 {n}편(연도 6개 × 50편) 중 셋 다 채움 {so['all_three_filled']}편 ({so['all_three_filled'] / n:.0%})"),
        ("3줄 뼈대 채움률 — 위치 대체 포함", "measured",
         f"같은 {n}편 중 셋 다 채움 {wf['all_three_filled']}편 ({wf['all_three_filled'] / n:.0%}). 위치 대체 카드는 '추정'으로 표시"),
        ("마스킹 기여(on/off)", *mask_row),
        ("약어 정밀도", "target", "목표 0.9 이상 · 3주차 초록 20편 검수 예정(미측정)"),
        ("추측·가능성 정밀도", "target", "목표 0.8 이상 · 3주차 초록 20편 검수 예정(미측정)"),
        ("규칙 재현율", "planned", "10편 소표본 점검 예정(미측정)"),
        ("규칙 테스트", "measured", "tests/ 폴더의 양성·음성·경계 사례. `py -I -m pytest`로 실행"),
    ]
    label = {"measured": "측정", "target": "목표", "planned": "예정"}
    body = "".join(f'<tr><td>{esc(t)}</td><td><span class="pp-tag {k}">{label[k]}</span></td><td>{esc(d)}</td></tr>'
                   for t, k, d in rows)
    st.markdown(f'<div class="pp-panel" style="padding:6px 8px"><table class="pp-table"><thead><tr><th>항목</th>'
                f'<th>상태</th><th>내용</th></tr></thead><tbody>{body}</tbody></table></div>', unsafe_allow_html=True)
    with st.expander("카드별 근거 분포(측정값)"):
        st.write({"신호 문구만": so["by_card"], "위치 대체 포함": wf["by_card"]})
    if bench and bench.get("analysis"):
        an = bench["analysis"]
        with st.expander("마스킹 실측 상세 — 손실을 하나씩 분류한 결과"):
            st.caption(an["metric_note"])
            st.markdown(f"**마스킹 끔에서 문자열이 바뀐 토큰 {an['off_lost_total']}개**")
            for title, items in (("값은 같고 표기만 바뀜", an["off_lost_benign"]),
                                 ("의미 있는 손실", an["off_lost_meaningful"]),
                                 ("탐지 오류(수정함)", an["off_lost_detection_error"])):
                st.markdown(f"- {title}: " + ", ".join(f"{k} {v}개" for k, v in items.items()))
            st.markdown("**마스킹 켬에서 생긴 문제**: " + ", ".join(f"{k} ({v}개)" for k, v in an["on_lost"].items()))
            st.markdown(f"**결정**: {an['decision']}")
            st.caption(f"설정: {bench['summary'].get('config', '')} · 전송량 약 {bench['summary'].get('chars_sent_approx', 0):,}자")
    st.markdown(sec_head("!", "알려진 한계"), unsafe_allow_html=True)
    st.markdown(
        "- 샘플은 연도별 연말 최신 제출 50편이라 대표성이 없어요.\n"
        "- `XGBoost`, `BiLSTM`, `k-NN` 같은 약어는 풀네임을 찾지 못해요(틀린 풀네임을 만들지 않고 '정의를 찾지 못함'으로 표시).\n"
        "- 추측 표시는 조동사 자체를 표시하며, 문장을 넘는 문맥은 보지 않아요.\n"
        "- 번역은 말투(~습니다/~한다)가 섞일 수 있어요.\n"
        "- PDF 2단 편집 순서는 복원하지 않아요. arXiv ID 입력을 권장해요.\n"
        "- 번역은 Claude Haiku 5.5(AI 번역, 키가 있을 때) 또는 DeepL이 해요. AI 번역은 드물게 뜻을 바꾸거나 빼먹을 수 있어 참고용이에요.\n"
        "- 번역 서비스 측의 데이터 보관은 각 서비스의 약관을 따르며, 이 앱이 따로 확인하지는 못했어요.")


# ================================================================ 메인

def main() -> None:
    st.set_page_config(page_title="PaperPath — 처음 읽는 영어 논문 도우미", page_icon="📄", layout="wide",
                       initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    topbar()
    page = st.session_state.page
    if page == PAGES[0]:
        reading_page()
    elif page == PAGES[1]:
        rules_page()
    else:
        validation_page()


main()
