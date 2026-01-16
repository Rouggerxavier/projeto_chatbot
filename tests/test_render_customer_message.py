from app import llm_service
from app import settings


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


def test_render_catalog_with_items(monkeypatch):
    facts = {
        "type": "catalog",
        "query": "cimento",
        "items": [
            {"id": "1", "name": "Cimento CP II", "price": "30.00", "unit": "UN"},
            {"id": "2", "name": "Cimento CP III", "price": "35.00", "unit": "UN"},
        ],
        "next_question": "Qual voce quer?",
    }
    _mock_groq(
        monkeypatch,
        "Aqui estao as opcoes:\n1) Cimento CP II\n2) Cimento CP III\n\nQual voce quer?",
    )
    out = llm_service.render_customer_message("CURTO_WHATSAPP", facts)
    assert out is not None
    assert "Cimento CP II" in out


def test_render_without_items_asks_question(monkeypatch):
    facts = {
        "type": "catalog",
        "query": "cimento",
        "items": [],
        "next_question": "Qual uso voce precisa?",
    }
    _mock_groq(monkeypatch, "Qual uso voce precisa?")
    out = llm_service.render_customer_message("NEUTRO", facts)
    assert out == "Qual uso voce precisa?"


def test_render_invalid_item_name(monkeypatch):
    facts = {
        "type": "catalog",
        "query": "cimento",
        "items": [{"id": "1", "name": "Cimento CP II", "price": "30.00", "unit": "UN"}],
        "next_question": "Qual voce quer?",
    }
    _mock_groq(monkeypatch, "- Tijolo 8 furos\nQual voce quer?")
    out = llm_service.render_customer_message("NEUTRO", facts)
    assert out is None


def test_render_invalid_price(monkeypatch):
    facts = {
        "type": "catalog",
        "query": "cimento",
        "items": [{"id": "1", "name": "Cimento CP II", "price": "", "unit": "UN"}],
        "next_question": "Qual voce quer?",
    }
    _mock_groq(monkeypatch, "Cimento CP II por R$ 10.00. Qual voce quer?")
    out = llm_service.render_customer_message("NEUTRO", facts)
    assert out is None


def test_maybe_render_disabled(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RENDERING_ENABLED", False)
    called = {"count": 0}

    def _render(*_args, **_kwargs):
        called["count"] += 1
        return "ok"

    monkeypatch.setattr(llm_service, "render_customer_message", _render)
    out = llm_service.maybe_render_customer_message("NEUTRO", {"type": "catalog"})
    assert out is None
    assert called["count"] == 0


def test_maybe_render_enabled_calls_renderer(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RENDERING_ENABLED", True)
    called = {"count": 0}

    def _render(*_args, **_kwargs):
        called["count"] += 1
        return "texto"

    monkeypatch.setattr(llm_service, "render_customer_message", _render)
    out = llm_service.maybe_render_customer_message("NEUTRO", {"type": "catalog"})
    assert out == "texto"
    assert called["count"] == 1


def test_maybe_render_enabled_fallback(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RENDERING_ENABLED", True)
    monkeypatch.setattr(llm_service, "render_customer_message", lambda *_: None)
    out = llm_service.maybe_render_customer_message("NEUTRO", {"type": "catalog"})
    assert out is None
