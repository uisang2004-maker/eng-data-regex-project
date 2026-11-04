"""Streamlit 화면 상태 테스트(AppTest). 네트워크를 쓰지 않는다."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def blank():
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


@pytest.fixture
def at(blank):
    """예시 문단을 불러온 화면."""
    blank.button(key="demo_btn").click().run()
    assert not blank.exception, blank.exception
    return blank


def md_text(at):
    return "\n".join(m.value for m in at.markdown)


def test_start_screen_hides_results_until_input(blank):
    text = "\n".join(m.value for m in blank.markdown if not m.value.lstrip().startswith("<style"))
    assert "끌어다 놓으세요" in text and "논문 넣기" in text
    assert 'class="pp-flow"' not in text and "pp-reader-title" not in text and "3줄 뼈대 ·" not in text
    assert blank.session_state["input_mode"] == "논문 PDF"
    assert not any(b.label == "번역하기" for b in blank.button)


def test_first_screen_shows_demo_skeleton_and_flag(at):
    text = md_text(at)
    assert "실제 논문 아님" in text
    assert "we introduce" in text and "신호 문구로 찾음" in text
    assert "약어 1" in text and "참조 1" in text


def test_translation_not_called_on_load(at, monkeypatch):
    # 번역 패널에는 '번역하기' 버튼만 있고 결과는 없다
    assert any(b.label == "번역하기" for b in at.button)
    assert at.session_state["translations"] == {}


def test_rule_toggle_keeps_input_and_changes_marks(at):
    at.session_state["input_text"] = "The method may be applied to images. These results suggest gains."
    at.toggle(key="show_steps").set_value(True).run()
    assert not at.exception
    before = md_text(at)
    assert 'class="pp-m hedge"' in before
    at.checkbox(key="rule_HEDGE").uncheck().run()
    after = md_text(at)
    assert not at.exception
    assert 'class="pp-m hedge"' not in after
    assert at.session_state["input_text"].startswith("The method may be applied")
    assert "HEDGE" not in at.session_state["active_rules"]


def test_rules_survive_hiding_steps_panel(at):
    at.toggle(key="show_steps").set_value(True).run()
    at.checkbox(key="rule_REFERENCE").uncheck().run()
    at.toggle(key="show_steps").set_value(False).run()
    assert "REFERENCE" not in at.session_state["active_rules"]
    assert "참조 0" in md_text(at)


def test_translation_result_survives_rule_toggle(at):
    import hashlib

    from src.extract import analyze
    from src.translate import TranslationResult

    a = analyze(at.session_state["input_text"])
    key = (hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16], True)
    fake = TranslationResult(ko=[f"번역 {i}" for i in range(len(a.sentences))], mode="aligned", protected=[[]] * len(a.sentences))
    at.session_state["translations"] = {key: fake}
    at.run()
    assert "번역 0" in md_text(at)
    at.toggle(key="show_steps").set_value(True).run()
    at.checkbox(key="rule_ABBR").uncheck().run()
    assert not at.exception
    assert "번역 0" in md_text(at)
    assert at.session_state["translations"][key].ko[0] == "번역 0"


def test_paste_validation_error(blank):
    blank.session_state["input_mode"] = "텍스트 붙여 넣기"
    blank.run()
    blank.text_area(key="paste_text").set_value("한국어 문장만 있어요.").run()
    blank.button(key="load_btn").click().run()
    assert any("영어 텍스트가 아닌" in e.value for e in blank.error)
    assert blank.session_state["show_input"] is True        # 실패하면 입력 칸이 그대로 열려 있다


def test_input_panel_closes_after_loading_and_reopens(at):
    keys = lambda: {b.key for b in at.button}
    assert "reinput_btn" in keys() and "load_btn" not in keys() and "demo_btn" not in keys()
    assert "pp-reader-title" in md_text(at)
    at.button(key="reinput_btn").click().run()
    assert "demo_btn" in keys() and "back_btn" in keys()
    assert not any("pp-reader-title" in m.value for m in at.markdown if not m.value.lstrip().startswith("<style"))
    at.button(key="back_btn").click().run()
    assert "reinput_btn" in keys() and at.session_state["input_text"]


def test_pages_render(at):
    for page in ("규칙 탐색", "검증 결과", "논문 읽기"):
        at.radio(key="page").set_value(page).run()
        assert not at.exception, page
    at.radio(key="page").set_value("검증 결과").run()
    assert "측정" in md_text(at)


def test_korean_highlights_follow_rules(at):
    import hashlib

    from src.extract import analyze
    from src.translate import TranslationResult

    a = analyze(at.session_state["input_text"])
    key = (hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16], True)
    ko = ["가"] * (len(a.sentences) - 1) + ["도움이 될 수 있음을 시사한다[4]."]
    km = [[] for _ in ko]
    km[-1] = [(11, 15, "hedge", "suggest"), (15, 18, "reference", "[4]")]
    at.session_state["translations"] = {key: TranslationResult(ko=ko, mode="aligned", ko_marks=km,
                                                               protected=[[]] * len(ko))}
    at.run()
    text = md_text(at)
    assert "영어 &#x27;suggest&#x27;에 대응" in text or "영어 'suggest'에 대응" in text
    at.toggle(key="show_steps").set_value(True).run()
    at.checkbox(key="rule_HEDGE").uncheck().run()
    text = md_text(at)
    assert "suggest&#x27;에 대응" not in text and "'suggest'에 대응" not in text
    assert "[4]&#x27;에 대응" in text or "'[4]'에 대응" in text


def test_cards_show_korean_and_underline(at):
    import hashlib

    from src.extract import analyze
    from src.translate import TranslationResult

    a = analyze(at.session_state["input_text"])
    key = (hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16], True)
    ko = [f"번역문 {i}입니다." for i in range(len(a.sentences))]
    uls = [(0, 3, "problem"), (0, 3, "method"), (0, 3, "result"), None]
    at.session_state["translations"] = {key: TranslationResult(ko=ko, mode="aligned", ko_underlines=uls,
                                                               ko_marks=[[] for _ in ko], protected=[[]] * len(ko))}
    at.run()
    text = md_text(at)
    assert 'class="pp-sk-ko"' in text and " 1입니다." in text   # "번역문"은 밑줄 태그로 감싸져 있다
    assert text.count('class="pp-u method"') >= 2   # 원문 카드·원문 패널·번역 쪽


def test_translation_blocked_after_session_limit(at, monkeypatch, tmp_path):
    from src import translate as T
    from src import usage

    # 가짜 DeepL 키(진짜 호출 전에 제한에서 막히는지만 본다)
    monkeypatch.setattr(T, "load_api_key", lambda name="DEEPL_API_KEY": "fake:fx" if name == "DEEPL_API_KEY" else None)
    at.session_state["deepl_calls"] = usage.MAX_CALLS_PER_SESSION
    at.session_state["input_text"] = "A short new sentence for testing limits. Another sentence here."
    at.run()
    at.button(key="translate_btn").click().run()
    assert not at.exception
    assert any("번까지" in w.value for w in at.warning)


def test_flow_and_glossary_section(at):
    text = md_text(at)
    assert "이해를 돕는 자료" in text and 'class="pp-flow"' in text
    assert "단어표 · " in text and "RAG" in text
    assert any(b.label.startswith("단어표 내려받기") for b in at.get("download_button"))


def test_ai_glossary_column_shows_when_present(at):
    import hashlib

    key = hashlib.sha256(at.session_state["input_text"].encode("utf-8")).hexdigest()[:16]
    assert "AI 풀이" not in md_text(at).split("어려운 단어표")[-1].split("</table>")[0]
    at.session_state["ai_gloss"] = {key: {"RAG": "검색 증강 생성"}}
    at.run()
    assert "검색 증강 생성" in md_text(at) and "참고용</span>" in md_text(at)
    assert next(b for b in at.button if b.key == "ai_gloss_btn").disabled      # 키 없음 + 이미 받음


def test_reading_modes(at):
    import hashlib

    from src.extract import analyze
    from src.translate import TranslationResult

    a = analyze(at.session_state["input_text"])
    key = (hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16], True)
    ko = [f"번역 {i}" for i in range(len(a.sentences))]
    at.session_state["translations"] = {key: TranslationResult(ko=ko, mode="aligned", ko_marks=[[] for _ in ko],
                                                               protected=[[]] * len(ko))}

    def view(mode):
        at.session_state["read_mode"] = mode
        at.run()
        assert not at.exception, mode
        return "\n".join(m.value for m in at.markdown if not m.value.lstrip().startswith("<style"))

    side = view("side")
    assert "영어 원문" in side and 'class="pp-sent pp-ko"' in side
    pair = view("pair")
    assert pair.count('class="pp-pair-ko"') == len(a.sentences) and 'class="pp-sent pp-ko"' not in pair
    en = view("en")
    assert "영어 원문" in en and 'class="pp-sent pp-ko"' not in en and "pp-pair-ko" not in en
    ko_only = view("ko")
    assert 'class="pp-sent pp-ko"' in ko_only and "영어 원문</span>" not in ko_only and "영어 원문 <span" not in ko_only


def test_frequent_term_tooltip_shows_meaning(at):
    import hashlib

    text = ("The reranker scores passages. A reranker is small. We train the reranker on data. "
            "Our reranker helps retrieval.")
    at.session_state["input_text"] = text
    at.run()
    before = md_text(at)
    assert "누르면 여기에 떠요" in before                                     # 뜻을 모르면 받는 방법 안내
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    at.session_state["ai_gloss"] = {key: {"reranker": "검색 결과 순위를 다시 매기는 모델"}}
    at.run()
    assert "reranker: 검색 결과 순위를 다시 매기는 모델" in md_text(at)


def test_korean_highlight_tooltip_matches_english(at):
    import hashlib
    import html as H

    from src.extract import analyze
    from src.translate import TranslationResult

    text = ("The reranker scores passages. A reranker is small. We train the reranker on data. "
            "Our reranker may help retrieval.")
    at.session_state["input_text"] = text
    a = analyze(text)
    tk = hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16]
    ko = ["재순위 모델이 문단에 점수를 매긴다.", "재순위 모델은 작다.", "우리는 재순위 모델을 학습한다.",
          "우리의 재순위 모델은 검색에 도움이 될 수 있다."]
    km = [[(0, 6, "term", "reranker")], [(0, 6, "term", "reranker")], [(4, 10, "term", "reranker")],
          [(4, 10, "term", "reranker"), (21, 25, "hedge", "may")]]
    at.session_state["translations"] = {(tk, True): TranslationResult(ko=ko, mode="aligned", ko_marks=km,
                                                                      protected=[[]] * 4)}
    at.session_state["ai_gloss"] = {tk: {"reranker": "검색 결과 순위를 다시 매기는 모델"}}
    at.run()
    out = H.unescape(md_text(at))
    assert "reranker: 검색 결과 순위를 다시 매기는 모델 · 이 글에 4번 · 영어 'reranker'에 대응" in out
    assert "추측·가능성" in out and "영어 'may'에 대응" in out


def test_tables_and_figures_inline_after_first_mention(at):
    from src.tables import TableInfo

    at.session_state["input_text"] = ("We describe the model. Results are in Table 1 and Figure 2. "
                                      "As Table 1 shows, the gains are large.")
    at.session_state["source"] = {"kind": "pdf", "title": "t", "section": "본문", "page": "본문"}
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    at.session_state["paper_tables"] = [TableInfo(1, "Table 1: Scores.", 3, png, width=400, height=100)]
    at.session_state["paper_figures"] = [TableInfo(2, "Figure 2: Curves.", 4, b"\xff\xd8xx", kind="figure",
                                                   width=300, height=200, mime="image/jpeg")]
    at.run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert ".pp-flt-table-1{background-image:url(data:image/png;base64," in text
    assert text.count('class="pp-float"') == 2                       # 표 1·그림 2, 처음 언급한 문장 아래 한 번씩
    assert 'class="pp-pop"' in text and "Table 1: 문장 2 아래에 있어요" in text   # 3번째 문장의 두 번째 언급


def test_tables_also_appear_in_korean_translation(at):
    import hashlib

    from src.extract import analyze
    from src.tables import TableInfo
    from src.translate import TranslationResult

    text = "We describe the model. Results are in Table 1. The gains are large."
    at.session_state["input_text"] = text
    at.session_state["source"] = {"kind": "pdf", "title": "t", "section": "본문", "page": "본문"}
    at.session_state["paper_tables"] = [TableInfo(1, "Table 1: Scores.", 3, b"\x89PNG", width=400, height=100)]
    a = analyze(text)
    tk = hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16]
    ko = ["모델을 설명한다.", "결과는 표 1에 있다.", "향상이 크다."]
    at.session_state["translations"] = {(tk, True): TranslationResult(ko=ko, mode="aligned", ko_marks=[[], [], []],
                                                                      protected=[[], [], []])}
    for mode, n in (("side", 2), ("ko", 1), ("en", 1), ("pair", 1)):
        at.session_state["read_mode"] = mode
        at.run()
        out = "\n".join(m.value for m in at.markdown)
        assert out.count('class="pp-float"') == n, mode          # 나란히 보기는 영어·한국어 쪽 둘 다
    at.session_state["read_mode"] = "ko"
    at.run()
    assert "<b>표 1</b>" in "\n".join(m.value for m in at.markdown)
