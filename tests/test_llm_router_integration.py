from typing import Dict, Any

from app import flow_controller


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
    }


def _noop(*args, **kwargs):
    return None


def test_router_show_catalog(monkeypatch):
    state = _base_state()
    state["awaiting_usage_context"] = False
    called = {"route": 0}

    def _route_intent(message, state_summary):
        called["route"] += 1
        return {
            "intent": "BROWSE_CATALOG",
            "product_query": "cimento",
            "category_hint": "cimento",
            "constraints": {},
            "action": "SHOW_CATALOG",
            "clarifying_question": None,
            "confidence": 0.9,
        }

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "route_intent", _route_intent)
    monkeypatch.setattr(flow_controller, "maybe_render_customer_message", lambda *_: None)
    monkeypatch.setattr(flow_controller, "save_chat_db", _noop)
    monkeypatch.setattr(flow_controller, "list_orcamento_items", lambda _: [])
    monkeypatch.setattr(flow_controller, "db_find_best_products", lambda *_: [])
    monkeypatch.setattr(flow_controller, "ask_usage_context", lambda *_: "Qual uso?")
    monkeypatch.setattr(flow_controller, "start_usage_context_flow", lambda *args, **kwargs: None)

    reply, _ = flow_controller.handle_message("vocês tem que tipo de cimento?", "s1")
    assert called["route"] == 1
    assert reply == "Qual uso?"


def test_router_bypass_pending_selection(monkeypatch):
    state = _base_state()
    state["last_suggestions"] = [{"id": 1, "nome": "Cimento CP II"}]

    def _route_intent(*args, **kwargs):
        raise AssertionError("route_intent nao deveria ser chamado")

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "route_intent", _route_intent)
    monkeypatch.setattr(flow_controller, "save_chat_db", _noop)
    monkeypatch.setattr(flow_controller, "handle_suggestions_choice", lambda *_: "ok")

    reply, _ = flow_controller.handle_message("2", "s1")
    assert reply == "ok"


def test_router_checkout_finalize_bypasses(monkeypatch):
    state = _base_state()

    def _route_intent(*args, **kwargs):
        raise AssertionError("route_intent nao deveria ser chamado")

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "route_intent", _route_intent)
    monkeypatch.setattr(flow_controller, "save_chat_db", _noop)
    monkeypatch.setattr(flow_controller, "handle_checkout", lambda *_: ("checkout", False))

    reply, _ = flow_controller.handle_message("quero finalizar", "s1")
    assert reply == "checkout"


def test_router_answer_with_rag_without_context(monkeypatch):
    state = _base_state()

    def _route_intent(message, state_summary):
        return {
            "intent": "TECHNICAL_QUESTION",
            "product_query": None,
            "category_hint": "cimento",
            "constraints": {},
            "action": "ANSWER_WITH_RAG",
            "clarifying_question": None,
            "confidence": 0.7,
        }

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "route_intent", _route_intent)
    monkeypatch.setattr(
        flow_controller,
        "plan_consultive_next_step",
        lambda *args, **kwargs: {
            "missing_fields": ["application"],
            "next_action": "ASK_CONTEXT",
            "next_question": "Qual uso?",
            "assumptions": [],
            "confidence": 0.8,
        },
    )
    monkeypatch.setattr(flow_controller, "save_chat_db", _noop)
    monkeypatch.setattr(flow_controller, "list_orcamento_items", lambda _: [])
    monkeypatch.setattr(flow_controller, "ask_usage_context", lambda *_: "Qual uso?")
    monkeypatch.setattr(flow_controller, "answer_consultive_question", lambda *_: ("nao deve chamar", False))

    reply, _ = flow_controller.handle_message("qual o melhor cimento?", "s1")
    assert reply == "Qual uso?"


def test_consultive_investigation_flow_uses_hint_check(monkeypatch):
    state = _base_state()
    state["consultive_investigation"] = True

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "save_chat_db", _noop)
    monkeypatch.setattr(flow_controller, "list_orcamento_items", lambda *_: [])
    monkeypatch.setattr(flow_controller, "maybe_render_customer_message", lambda *_: None)
    monkeypatch.setattr(flow_controller, "_should_bypass_router", lambda *_: True)
    monkeypatch.setattr(flow_controller, "extract_product_hint", lambda *_: "esmalte")
    monkeypatch.setattr(flow_controller, "is_generic_product", lambda *_: False)
    monkeypatch.setattr(
        "app.flows.consultive_investigation.continue_investigation",
        lambda *_: "investigacao ok",
    )

    reply, _ = flow_controller.handle_message("quero esmalte", "s1")
    assert reply == "investigacao ok"


def test_router_low_confidence_returns_clarify(monkeypatch):
    state = _base_state()
    monkeypatch.setattr(flow_controller.settings, "ROUTER_CONFIDENCE_THRESHOLD", 0.65)
    monkeypatch.setattr(flow_controller.settings, "LLM_HARD_BLOCK_THRESHOLD", 0.40)

    def _route_intent(message, state_summary):
        return {
            "intent": "BROWSE_CATALOG",
            "product_query": "cimento",
            "category_hint": "cimento",
            "constraints": {},
            "action": "SHOW_CATALOG",
            "clarifying_question": None,
            "confidence": 0.20,
        }

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("catalog/search should not run on low confidence")

    monkeypatch.setattr(flow_controller, "get_state", lambda _: state)
    monkeypatch.setattr(flow_controller, "route_intent", _route_intent)
    monkeypatch.setattr(flow_controller, "save_chat_db", _noop)
    monkeypatch.setattr(flow_controller, "db_find_best_products", _raise_if_called)
    monkeypatch.setattr(flow_controller, "maybe_render_customer_message", lambda *_: None)
    monkeypatch.setattr(flow_controller, "ask_usage_context", _raise_if_called)
    monkeypatch.setattr(flow_controller, "start_usage_context_flow", _raise_if_called)

    reply, _ = flow_controller.handle_message("vocǦs tem que tipo de cimento?", "s1")
    assert "Preciso confirmar" in reply
