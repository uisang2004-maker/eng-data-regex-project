"""내 계정 저장(C) 테스트: 실제 Supabase·Google 로그인 없이 메모리 저장소와 가짜 HTTP로 확인한다."""

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src import store as S

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_user_key_hides_login_id():
    k = S.user_key("google-sub-123", "salt")
    assert k == S.user_key("google-sub-123", "salt") and "google" not in k and len(k) == 32
    assert k != S.user_key("google-sub-123", "other") and k != S.user_key("google-sub-124", "salt")


def test_memory_store_roundtrip_and_delete():
    s = S.MemoryStore()
    s.put_items("u1", {"h1": {"t": {}, "g": {"x": "뜻"}, "ts": 1}})
    s.put_docs("u1", {"d1": {"id": "d1"}})
    s.put_docs("u2", {"d2": {"id": "d2"}})
    assert s.load_all("u1") == ({"h1": {"t": {}, "g": {"x": "뜻"}, "ts": 1}}, {"d1": {"id": "d1"}})
    s.delete_doc("u1", "d1")
    assert s.load_all("u1")[1] == {}
    s.delete_all("u1")
    assert s.load_all("u1") == ({}, {}) and s.load_all("u2")[1] == {"d2": {"id": "d2"}}


def test_supabase_requests(monkeypatch):
    sent = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout, context):
        sent.append(req)
        if req.get_method() == "GET" and "paperpath_items" in req.full_url:
            return Resp(json.dumps([{"text_hash": "h1", "item": {"g": {}}}]).encode())
        return Resp(b"[]" if req.get_method() == "GET" else b"")

    monkeypatch.setattr(S.urllib.request, "urlopen", fake_urlopen)
    s = S.SupabaseStore("https://abc.supabase.co", "service-key")
    items, docs = s.load_all("u1")
    assert items == {"h1": {"g": {}}} and docs == {}
    assert "user_id=eq.u1" in sent[0].full_url and sent[0].get_header("Apikey") == "service-key"
    s.put_items("u1", {f"h{i}": {"g": {}} for i in range(120)})
    posts = [r for r in sent if r.get_method() == "POST"]
    assert len(posts) == 3 and "merge-duplicates" in posts[0].get_header("Prefer")     # 50개씩 나눠 올림
    assert json.loads(posts[0].data)[0]["user_id"] == "u1"


def test_supabase_errors_become_store_error(monkeypatch):
    def boom(req, timeout, context):
        raise S.urllib.error.URLError("down")

    monkeypatch.setattr(S.urllib.request, "urlopen", boom)
    with pytest.raises(S.StoreError):
        S.SupabaseStore("https://abc.supabase.co", "k").load_all("u1")


@pytest.fixture
def logged_in(monkeypatch):
    monkeypatch.setenv("PAPERPATH_TEST_STORE", "1")
    st.cache_resource.clear()
    yield monkeypatch
    st.cache_resource.clear()


def new_session(mp, user: str):
    mp.setenv("PAPERPATH_TEST_USER", user)       # 테스트가 끝나면 monkeypatch가 되돌린다
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def test_results_follow_the_account_to_another_session(logged_in):
    import hashlib

    from src.extract import analyze
    from src.translate import TranslationResult

    at = new_session(logged_in, "alice")
    assert any(b.key == "logout_btn" for b in at.button)
    at.button(key="demo_btn").click().run()
    a = analyze(at.session_state["input_text"])
    key = hashlib.sha256(a.text.encode("utf-8")).hexdigest()[:16]
    ko = [f"번역 {i}" for i in range(len(a.sentences))]
    at.session_state["translations"] = {(key, True): TranslationResult(ko=ko, mode="aligned",
                                                                      ko_marks=[[] for _ in ko], protected=[[]] * len(ko))}
    at.run()                                         # 다음 실행에서 내 계정에 올린다

    other_pc = new_session(logged_in, "alice")                  # 다른 PC(새 화면)에서 같은 계정
    assert other_pc.session_state["translations"][(key, True)].ko == ko
    stranger = new_session(logged_in, "bob")                    # 다른 사람에게는 보이지 않는다
    assert (key, True) not in stranger.session_state["translations"]


def test_login_hidden_without_settings(monkeypatch):
    monkeypatch.delenv("PAPERPATH_TEST_STORE", raising=False)
    monkeypatch.delenv("PAPERPATH_TEST_USER", raising=False)
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not any(b.key in ("login_btn", "logout_btn") for b in at.button)


def test_supabase_error_detail_and_nul_removed(monkeypatch):
    import io

    sent = []

    def fake_urlopen(req, timeout, context):
        sent.append(req)
        raise S.urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                       io.BytesIO(b'{"message":"Invalid API key"}'))

    monkeypatch.setattr(S.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(S.StoreError, match="401 · Invalid API key"):
        S.SupabaseStore("https://abc.supabase.co", "k").put_docs("u1", {"d": {"text": "a\x00b"}})
    assert b"\u0000" not in sent[0].data and "ab" in json.loads(sent[0].data)[0]["doc"]["text"]
