import json
from typing import Dict, Any

from app import llm_service
from app import flow_controller


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


def _base_state() -> Dict[str, Any]:
    return {
        "checkout_mode": False,
        "asking_for_more": False,
        "awaiting_qty": False,
        "pending_product_id": None,
        "awaiting_remove_choice": False,
        "awaiting_remove_qty": False,
        "awaiting_usage_context": False,
        "consultive_investigation": False,
        "last_suggestions": [],
        "last_hint": None,
        "consultive_product_hint": None,
        "asked_context_fields": [],
        "consultive_application": None,
        "consultive_environment": None,
        "consultive_exposure": None,
        "consultive_load_type": None,
        "consultive_surface": None,
        "consultive_grain": None,
        "consultive_size": None,
    }


def test_planner_cimento_laje_externa(monkeypatch):
    payload = {
        "missing_fields": ["load_type"],
        "next_action": "ASK_CONTEXT",
        "next_question": "Uso residencial ou carga pesada?",
        "assumptions": [],
        "confidence": 0.78,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.plan_consultive_next_step(
        "qual melhor cimento pra laje externa?",
        {},
        "cimento",
        {},
    )
    assert out and out["next_action"] == "ASK_CONTEXT"
    assert "carga" in out["next_question"].lower()


def test_planner_tinta_banheiro(monkeypatch):
    payload = {
        "missing_fields": ["environment"],
        "next_action": "ASK_CONTEXT",
        "next_question": "Vai usar no box (umidade direta) ou parede externa?",
        "assumptions": [],
        "confidence": 0.72,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.plan_consultive_next_step(
        "tinta pro banheiro",
        {},
        "tinta",
        {},
    )
    assert out and out["next_action"] == "ASK_CONTEXT"
    assert out["next_question"]


def test_planner_tijolo_muro(monkeypatch):
    payload = {
        "missing_fields": ["application"],
        "next_action": "ASK_CONTEXT",
        "next_question": "Voce precisa de tijolo estrutural ou de vedacao?",
        "assumptions": [],
        "confidence": 0.74,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.plan_consultive_next_step(
        "tijolo pra muro",
        {},
        "tijolo",
        {},
    )
    assert out and out["next_action"] == "ASK_CONTEXT"
    assert "vedacao" in out["next_question"].lower()


def test_planner_ready_to_answer(monkeypatch):
    payload = {
        "missing_fields": [],
        "next_action": "READY_TO_ANSWER",
        "next_question": None,
        "assumptions": [],
        "confidence": 0.8,
    }
    _mock_groq(monkeypatch, json.dumps(payload))
    out = llm_service.plan_consultive_next_step(
        "qual melhor cimento pra laje externa?",
        {},
        "cimento",
        {"application": "laje", "environment": "externa"},
    )
    assert out and out["next_action"] == "READY_TO_ANSWER"


def test_planner_invalid_json(monkeypatch):
    _mock_groq(monkeypatch, "nao eh json")
    out = llm_service.plan_consultive_next_step("teste", {}, "cimento", {})
    assert out is None


def test_planner_invalid_json_fallback(monkeypatch):
    state = _base_state()

    def _route_intent(message, state_summary):
        return {
            "intent": "TECHNICAL_QUESTION",
            "product_query": "cimento",
            "category_hint": "cimento",
            "constraints": {},
            "action": "ASK_USAGE_CONTEXT",
            "clarifying_question": None,
            "confidence": 0.9,
        }

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "route_intent", _route_intent)
    monkeypatch.setattr(flow_controller, "plan_consultive_next_step", lambda *_: None)
    monkeypatch.setattr(flow_controller, "ask_usage_context", lambda *_: "Qual uso?")
    monkeypatch.setattr(flow_controller, "save_chat_db", lambda *_: None)
    monkeypatch.setattr(flow_controller, "list_orcamento_items", lambda *_: [])
    monkeypatch.setattr(flow_controller, "patch_state", lambda *_: None)

    reply, _ = flow_controller.handle_message("quero cimento", "s1")
    assert reply == "Qual uso?"
