import json

from app import llm_service
from app.flows import technical_recommendations


class _FakeResp:
    def __init__(self, content: str):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


class _FakeGroq:
    def __init__(self, content: str):
        self._content = content
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        return _FakeResp(self._content)


def _mock_groq(monkeypatch, content: str):
    monkeypatch.setattr(llm_service, "_get_groq_client", lambda: _FakeGroq(content))


def test_tinta_requires_surface_and_env():
    ctx = {"product": "tinta", "surface": "parede", "environment": "interna"}
    assert technical_recommendations.can_generate_technical_answer("tinta", ctx) is True

    ctx_missing = {"product": "tinta", "surface": "parede"}
    assert technical_recommendations.can_generate_technical_answer("tinta", ctx_missing) is False


def test_generate_synthesis_tinta_without_application(monkeypatch):
    payload = "Sintese tecnica tinta interna."
    _mock_groq(monkeypatch, payload)
    ctx = {"product": "tinta", "surface": "parede", "environment": "interna"}
    out = llm_service.generate_technical_synthesis("tinta", ctx, ["acabamento"])
    assert out  # deve gerar mesmo sem application


def test_generate_synthesis_tinta_missing_env(monkeypatch):
    payload = "Sintese tecnica tinta interna."
    _mock_groq(monkeypatch, payload)
    ctx = {"product": "tinta", "surface": "parede"}  # faltando environment
    out = llm_service.generate_technical_synthesis("tinta", ctx, ["acabamento"])
    assert out == ""
