"""논문 독해 도우미 — Phase 2 프로토타입 (Streamlit).

실행: .venv/Scripts/python.exe -m streamlit run prototype/paper-reader/app.py
"""

import html
import json
from collections import Counter
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import rules

HERE = Path(__file__).parent
SAMPLE_PATH = HERE / "data" / "sample_abstracts.jsonl"

# 기능 시연을 위해 직접 작성한 본문 예시 (실제 논문 아님). PDF 복사처럼 줄바꿈·하이픈을 일부러 넣었다.
DEMO_TEXT = """Large language models (LLMs) have become the default tool for many tasks in Natural Language Processing (NLP). However, little is known about how they handle domain-specific termi-
nology, and existing methods struggle to explain their errors [3, 5].

In this paper, we propose Rule-Visible Reading Support (RVRS), a lightweight framework that marks hedges, boosters and acronyms with regular expressions. Our approach does not require any training and may be applied to any English text.

Experiments on 300 abstracts show that RVRS recovers 87% of acronym definitions (Table 2), which suggests that
simple patterns may capture a large part of what readers need. As shown in Fig. 3, LLMs tend to produce longer sentences than human authors (Smith et al., 2021). We demonstrate that the difference is significantly larger in recent years (Section 5.1).

A limitation of our study is that RVRS is limited to English computer science papers; we leave other fields for future work. The utilization of nominalized expressions was not considered in the evaluation of readability."""

CATEGORY_STYLE = {
    "acronym": "border-bottom:2px dotted #047857;font-weight:600;color:inherit",
    "acronym-unknown": "border-bottom:2px dotted #9ca3af;color:inherit",
    "hedge": "background:#fde68a;color:#111;border-radius:3px;padding:0 2px",
    "booster": "background:#a5f3fc;color:#111;border-radius:3px;padding:0 2px",
    "ref": "background:#e9d5ff;color:#111;border-radius:3px;padding:0 2px",
}
SKELETON_COLOR = {"problem": "#ef4444", "method": "#10b981", "result": "#3b82f6", "limit": "#8b5cf6"}
SKELETON_LABEL = {r.category: r.label for r in rules.SKELETON_RULES}
LAYER_OF = {"acronym": "약어", "acronym-unknown": "약어", "hedge": "추측·확신", "booster": "추측·확신", "ref": "참조"}


@st.cache_data
def load_samples() -> list[dict]:
    with SAMPLE_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def render(result: dict, layers: set[str]) -> str:
    text, spans = result["text"], result["spans"]
    out = []
    for sent in result["sentences"]:
        s, e = sent["start"], sent["end"]
        pieces, pos = [], s
        for a, b, cat, tip in spans:
            if b <= s or a >= e or LAYER_OF[cat] not in layers:
                continue
            pieces.append(html.escape(text[pos:a]))
            pieces.append(f'<span style="{CATEGORY_STYLE[cat]}" title="{html.escape(tip)}">{html.escape(text[a:b])}</span>')
            pos = b
        pieces.append(html.escape(text[pos:e]))
        inner = "".join(pieces)

        badges = ""
        style = ""
        if "뼈대" in layers and sent["tags"]:
            first = sent["tags"][0]
            style = f"border-bottom:3px solid {SKELETON_COLOR[first.category]};"
            for t in sent["tags"]:
                badges += (f'<sup style="background:{SKELETON_COLOR[t.category]};color:#fff;border-radius:4px;'
                           f'padding:0 4px;margin-left:3px;font-size:11px" title="규칙 {t.name}">{t.label}</sup>')
        if "난이도" in layers and sent["difficulty"]["level"] == "어려움":
            d = sent["difficulty"]
            badges += (f'<sup style="background:#374151;color:#fff;border-radius:4px;padding:0 4px;margin-left:3px;font-size:11px" '
                       f'title="단어 {d["words"]} · 수동태 {d["passive"]} · 명사화 {d["nominal"]}">어려움</sup>')
        out.append(f'<span style="{style}">{inner}</span>{badges} ')
        if text[e:e + 2] == "\n\n" or "\n\n" in text[e:e + 4]:
            out.append("<br><br>")
    return f'<div style="line-height:2.1;font-size:16px">{"".join(out)}</div>'


def legend(layers: set[str]) -> str:
    items = []
    if "약어" in layers:
        items += [(CATEGORY_STYLE["acronym"], "약어(풀네임 툴팁)"), (CATEGORY_STYLE["acronym-unknown"], "정의 없는 약어")]
    if "추측·확신" in layers:
        items += [(CATEGORY_STYLE["hedge"], "추측(hedge)"), (CATEGORY_STYLE["booster"], "확신(booster)")]
    if "참조" in layers:
        items += [(CATEGORY_STYLE["ref"], "인용·그림·표 참조")]
    if "뼈대" in layers:
        items += [(f"border-bottom:3px solid {c}", SKELETON_LABEL[k] + " 문장") for k, c in SKELETON_COLOR.items()]
    return " ".join(f'<span style="{s};margin-right:10px;font-size:13px">{html.escape(t)}</span>' for s, t in items)


# ================================================================ 화면

st.set_page_config(page_title="논문 독해 도우미 (프로토타입)", page_icon="📖", layout="wide")
st.title("📖 논문 독해 도우미")
st.caption("Phase 2 프로토타입 · 모든 표시는 **정규표현식 규칙**의 결과입니다(AI 모델 사용 안 함). 하이라이트에 마우스를 올리면 어떤 규칙이 잡았는지 보입니다.")

tab_read, tab_stats, tab_rules = st.tabs(["독해 도우미", "샘플 분석 (arXiv 초록)", "규칙 보기"])

samples = load_samples()

with tab_read:
    options = ["직접 작성한 본문 예시 (기능 시연용, 실제 논문 아님)"] + [
        f"샘플 arXiv 초록 · {r['year']} · {r['title'][:70]}" for r in samples
    ]

    def _load_example():
        idx = options.index(st.session_state.example)
        st.session_state.text = DEMO_TEXT if idx == 0 else samples[idx - 1]["abstract"]

    if "text" not in st.session_state:
        st.session_state.text = DEMO_TEXT

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.selectbox("예시 불러오기", options, key="example", on_change=_load_example)
        st.text_area("논문 텍스트를 붙여 넣으세요 (초록·본문 모두 가능)", key="text", height=420)
        layers = set(st.pills("표시할 층", ["뼈대", "약어", "추측·확신", "참조", "난이도"],
                              selection_mode="multi", default=["뼈대", "약어", "추측·확신", "참조", "난이도"]) or [])
        st.caption("저장하지 않습니다. 붙여 넣은 텍스트는 이 화면에서만 처리됩니다.")

    result = rules.analyze(st.session_state.text)
    c = result["counts"]
    with right:
        n100 = max(result["n_words"], 1) / 100
        m = st.columns(5)
        m[0].metric("단어", result["n_words"])
        m[1].metric("약어", sum(1 for v in result["acronyms"].values() if v), help="풀네임을 찾은 약어 수")
        m[2].metric("추측 / 100단어", f"{c.get('hedge', 0) / n100:.1f}")
        m[3].metric("확신 / 100단어", f"{c.get('booster', 0) / n100:.1f}")
        m[4].metric("참조", c.get("ref", 0))

        if "뼈대" in layers:
            st.markdown("##### 이 글의 뼈대")
            cols = st.columns(4)
            for col, rule in zip(cols, rules.SKELETON_RULES):
                hits = [s for s in result["sentences"] if rule in s["tags"]]
                with col:
                    st.markdown(f'<div style="border-top:4px solid {SKELETON_COLOR[rule.category]};padding-top:4px">'
                                f"<b>{rule.label}</b> <small>({len(hits)}문장)</small></div>", unsafe_allow_html=True)
                    st.caption(hits[0]["text"][:220] + ("…" if len(hits[0]["text"]) > 220 else "") if hits else "찾지 못함")

        st.markdown("##### 색칠된 본문")
        st.markdown(legend(layers), unsafe_allow_html=True)
        st.markdown(render(result, layers), unsafe_allow_html=True)

        if "약어" in layers and result["acronyms"]:
            st.markdown("##### 약어 사전")
            st.dataframe(pd.DataFrame([{"약어": k, "풀네임": v or "(이 글에서 정의를 찾지 못함)"}
                                       for k, v in result["acronyms"].items()]), hide_index=True, width="stretch")

        if "난이도" in layers and result["sentences"]:
            st.markdown("##### 문장별 난이도")
            df = pd.DataFrame([{"문장": i + 1, "점수": s["difficulty"]["score"], "수준": s["difficulty"]["level"],
                                "단어": s["difficulty"]["words"], "수동태": s["difficulty"]["passive"],
                                "명사화": s["difficulty"]["nominal"], "내용": s["text"][:80]}
                               for i, s in enumerate(result["sentences"])])
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X("문장:O"), y=alt.Y("점수:Q", title="난이도 점수"),
                color=alt.Color("수준:N", scale=alt.Scale(domain=["쉬움", "보통", "어려움"],
                                                        range=["#86efac", "#fcd34d", "#f87171"])),
                tooltip=["문장", "점수", "단어", "수동태", "명사화", "내용"])
            st.altair_chart(chart, width="stretch")
            st.caption("점수 = 단어 수 + 6×수동태 + 3×명사화(-tion, -ment 등). 30 미만 쉬움, 50 이상 어려움 (임시 기준).")

with tab_stats:
    st.info(f"**샘플** · arXiv cs.CL 초록 {len(samples)}건 (연도별 해당 연도 말 최신 제출 50건씩). "
            "대표성이 없는 소량 샘플이라 추세는 참고용입니다. 메타데이터 CC0 1.0.")

    @st.cache_data
    def sample_stats() -> tuple[pd.DataFrame, Counter]:
        rows, acr = [], Counter()
        for r in load_samples():
            a = rules.analyze(r["abstract"])
            n100 = max(a["n_words"], 1) / 100
            defined = {k: v for k, v in a["acronyms"].items() if v}
            acr.update(defined.keys())
            rows.append({
                "year": r["year"],
                "약어 정의 수": len(defined),
                "정의 없는 약어 수": sum(1 for v in a["acronyms"].values() if not v),
                "추측 / 100단어": a["counts"].get("hedge", 0) / n100,
                "확신 / 100단어": a["counts"].get("booster", 0) / n100,
                "평균 문장 길이(단어)": a["n_words"] / max(len(a["sentences"]), 1),
                **{f"{r_.label} 문장 있음": any(r_ in s["tags"] for s in a["sentences"]) for r_ in rules.SKELETON_RULES},
            })
        return pd.DataFrame(rows), acr

    df, acr = sample_stats()
    by_year = df.groupby("year").mean(numeric_only=True).reset_index()

    def line(cols: list[str], title: str):
        long = by_year.melt("year", cols, "지표", "값")
        return alt.Chart(long, title=title).mark_line(point=True).encode(
            x=alt.X("year:O", title="연도"), y=alt.Y("값:Q", title=None), color="지표:N",
            tooltip=["year", "지표", alt.Tooltip("값:Q", format=".2f")]).properties(height=260)

    a1, a2 = st.columns(2)
    a1.altair_chart(line(["약어 정의 수", "정의 없는 약어 수"], "초록 1편당 약어"), width="stretch")
    a2.altair_chart(line(["추측 / 100단어", "확신 / 100단어"], "100단어당 추측·확신 표현"), width="stretch")
    b1, b2 = st.columns(2)
    b1.altair_chart(line(["평균 문장 길이(단어)"], "평균 문장 길이"), width="stretch")
    sk_cols = [f"{r.label} 문장 있음" for r in rules.SKELETON_RULES]
    b2.altair_chart(line(sk_cols, "뼈대 문장이 잡힌 초록 비율"), width="stretch")

    st.markdown("##### 샘플에서 가장 많이 정의된 약어")
    st.dataframe(pd.DataFrame(acr.most_common(15), columns=["약어", "정의된 초록 수"]), hide_index=True)

with tab_rules:
    st.markdown("화면의 모든 표시는 아래 규칙에서 나옵니다. 컨펌 후 `src/patterns.py`로 옮기고 테스트를 붙일 예정입니다.")
    rows = [{"규칙": r.name, "층": r.label, "설명": r.desc, "예시": ", ".join(r.examples), "패턴": r.pattern.pattern}
            for r in rules.TOKEN_RULES + rules.SKELETON_RULES]
    rows += [
        {"규칙": "ACRONYM_DEF", "층": "약어", "설명": "괄호 안 약어 후보 + 앞 단어 첫 글자 맞춤", "예시": "Natural Language Processing (NLP)",
         "패턴": rules.ACRONYM_DEF.pattern},
        {"규칙": "BARE_ACRONYM", "층": "약어", "설명": "정의 없이 쓰인 대문자 약어", "예시": "GPU", "패턴": rules.BARE_ACRONYM.pattern},
        {"규칙": "DEHYPHEN", "층": "전처리", "설명": "PDF 줄바꿈 하이픈 제거", "예시": "termi-\\nnology → terminology",
         "패턴": rules.DEHYPHEN.pattern},
        {"규칙": "PASSIVE", "층": "난이도", "설명": "be동사 + 과거분사", "예시": "was not considered", "패턴": rules.PASSIVE.pattern},
        {"규칙": "NOMINAL", "층": "난이도", "설명": "명사화 접미사", "예시": "utilization, evaluation", "패턴": rules.NOMINAL.pattern},
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
