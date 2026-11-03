"""Streamlit 화면 상태 테스트(AppTest). 네트워크를 쓰지 않는다."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def at():
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def md_text(at):
    return "\n".join(m.value for m in at.markdown)


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


def test_paste_validation_error(at):
    at.session_state["input_mode"] = "텍스트 붙여 넣기"
    at.run()
    at.text_area(key="paste_text").set_value("한국어 문장만 있어요.").run()
    at.button(key="load_btn").click().run()
    assert any("영어 텍스트가 아닌" in e.value for e in at.error)


def test_pages_render(at):
    for page in ("규칙 탐색", "검증 결과", "논문 읽기"):
        at.radio(key="page").set_value(page).run()
        assert not at.exception, page
    at.radio(key="page").set_value("검증 결과").run()
    assert "측정" in md_text(at)
