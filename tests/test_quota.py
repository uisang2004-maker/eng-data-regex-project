"""사용자별 번역 한도: 로그인 하루 새 논문 1편(한 편 하루 6만 자), 비로그인 맛보기 3,000자."""

import hashlib
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src import quota as Q

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_one_new_paper_per_day():
    day = {}
    assert Q.check_user(day, "p1", False, 5_000) is None
    day = Q.add_user(day, "p1", False, 5_000)
    assert Q.check_user(day, "p1", False, 20_000) is None              # 같은 논문은 계속
    assert "새 논문 1편" in Q.check_user(day, "p2", False, 1_000)       # 두 번째 새 논문은 막힘
    assert Q.check_user(day, "old", True, 1_000) is None                # 예전에 시작한 논문 이어 번역은 허용
    day = Q.add_user(day, "old", True, 1_000)
    assert Q.new_papers(day) == 1 and day["docs"]["old"]["new"] is False


def test_per_paper_daily_chars():
    day = Q.add_user({}, "p1", False, Q.MAX_CHARS_PER_PAPER - 500)
    assert Q.check_user(day, "p1", False, 400) is None
    assert "6" in Q.check_user(day, "p1", False, 600)


def test_guest_trial():
    assert Q.check_guest(0, 2_500) is None
    assert "로그인" in Q.check_guest(2_500, 1_000)


def fake_engine(monkeypatch):
    """번역 API 대신 문장 앞에 KO:를 붙이는 가짜(Claude 엔진으로 보이게)."""
    import re

    from src import translate as T

    def fake(texts, key, split):
        return [re.sub(r"<s>", "<s>KO:", t) for t in texts]

    monkeypatch.setattr(T, "pick_engine", lambda c, d: ("claude", "fake-key", fake))


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("PAPERPATH_TEST_STORE", "1")
    st.cache_resource.clear()
    fake_engine(monkeypatch)
    yield monkeypatch
    st.cache_resource.clear()


def paste(at, text):
    at.session_state["input_mode"] = "텍스트 붙여 넣기"
    at.run()
    at.text_area(key="paste_text").set_value(text).run()
    at.button(key="load_btn").click().run()
    assert not at.exception, at.exception


def translate(at):
    at.button(key="translate_btn").click().run()
    assert not at.exception, at.exception
    key = hashlib.sha256(at.session_state["input_text"].encode("utf-8")).hexdigest()[:16]
    return at.session_state["translations"][(key, True)]


def test_logged_in_user_gets_one_new_paper_per_day(env):
    env.setenv("PAPERPATH_TEST_USER", "carol")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    paste(at, "We propose a small model for reading. It works well on two tasks.")
    assert translate(at).ko is not None                                 # 첫 논문: 번역됨
    at.button(key="reinput_btn").click().run()
    paste(at, "Another paper studies retrieval. The results are strong.")
    res = translate(at)
    assert res.ko is None and "새 논문 1편" in res.error               # 두 번째 새 논문: 막힘


def test_guest_is_limited_to_trial(env):
    env.delenv("PAPERPATH_TEST_USER", raising=False)
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    paste(at, "Short abstract text. " * 200)                            # 약 4,200자
    res = translate(at)
    assert res.ko is None and "로그인" in res.error
