"""모든 테스트 공통: 로컬 .env의 실제 API 키를 읽지 않게 막는다(테스트가 유료 번역을 부르지 않도록)."""

import pytest

from src import translate as T


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    monkeypatch.setattr(T, "load_api_key", lambda name="DEEPL_API_KEY": None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
