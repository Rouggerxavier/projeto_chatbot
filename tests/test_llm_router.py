import json

from app import llm_service


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


def test_route_browse_catalog_cimento(monkeypatch):
    payload = {
        "intent": "BROWSE_CATALOG",
        "product_query": "cimento",
        "category_hint": "cimento",
        "constraints": {},
        "action": "SHOW_CATALOG",
        "clarifying_question": None,
        "confidence": 0.88,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.route_intent("vocês tem que tipo de cimento?", {})
    assert out and out["intent"] == "BROWSE_CATALOG"
    assert out["action"] == "SHOW_CATALOG"


def test_route_browse_catalog_tijolo(monkeypatch):
    payload = {
        "intent": "BROWSE_CATALOG",
        "product_query": "tijolo 8 furos",
        "category_hint": "tijolo",
        "constraints": {"tipo": "8 furos"},
        "action": "SHOW_CATALOG",
        "clarifying_question": None,
        "confidence": 0.82,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.route_intent("tem tijolo 8 furos?", {})
    assert out and out["category_hint"] == "tijolo"
    assert out["action"] == "SHOW_CATALOG"


def test_route_technical_question(monkeypatch):
    payload = {
        "intent": "TECHNICAL_QUESTION",
        "product_query": "tinta",
        "category_hint": "tinta",
        "constraints": {"surface": "parede", "environment": "externa"},
        "action": "ANSWER_WITH_RAG",
        "clarifying_question": None,
        "confidence": 0.76,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.route_intent("qual a melhor tinta pra parede externa?", {})
    assert out and out["intent"] == "TECHNICAL_QUESTION"
    assert out["action"] == "ANSWER_WITH_RAG"


def test_route_checkout(monkeypatch):
    payload = {
        "intent": "CHECKOUT",
        "product_query": None,
        "category_hint": None,
        "constraints": {},
        "action": "HANDOFF_CHECKOUT",
        "clarifying_question": None,
        "confidence": 0.91,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.route_intent("quero finalizar o pedido", {})
    assert out and out["action"] == "HANDOFF_CHECKOUT"


def test_route_unknown(monkeypatch):
    payload = {
        "intent": "UNKNOWN",
        "product_query": None,
        "category_hint": None,
        "constraints": {},
        "action": "ASK_CLARIFYING_QUESTION",
        "clarifying_question": "Pode explicar melhor o que precisa?",
        "confidence": 0.4,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.route_intent("hmm", {})
    assert out and out["intent"] == "UNKNOWN"


def test_route_invalid_json(monkeypatch):
    _mock_groq(monkeypatch, "nao eh json")
    out = llm_service.route_intent("teste", {})
    assert out is None


def test_route_invalid_schema(monkeypatch):
    payload = {
        "intent": "BROWSE_CATALOG",
        "product_query": "cimento",
        "category_hint": "cimento",
        "constraints": {},
        "action": "INVALID",
        "clarifying_question": None,
        "confidence": 0.6,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.route_intent("teste", {})
    assert out is None
