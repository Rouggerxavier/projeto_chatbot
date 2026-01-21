from typing import Dict, Any

from app import flow_controller


def test_interruption_and_resume(monkeypatch):
    state: Dict[str, Any] = {
        "pending_prompt": {
            "text": "Quer adicionar outro produto? (sim ou nao)",
            "expected_kind": "yes_no",
            "metadata": {},
        },
        "state_stack": [],
        "asking_for_more": True,
        "checkout_mode": False,
        "awaiting_qty": False,
        "awaiting_remove_choice": False,
        "awaiting_remove_qty": False,
        "awaiting_usage_context": False,
        "consultive_investigation": False,
        "last_suggestions": [],
        "last_hint": None,
    }

    def _get_state(_):
        return state

    def _set_pending(user_id, prompt):
        state["pending_prompt"] = prompt

    def _push_pending(user_id, prompt):
        stack = list(state.get("state_stack") or [])
        stack.append(prompt)
        state["state_stack"] = stack

    def _pop_pending(user_id):
        stack = list(state.get("state_stack") or [])
        if not stack:
            state["state_stack"] = []
            return None
        prompt = stack.pop()
        state["state_stack"] = stack
        return prompt

    monkeypatch.setattr(flow_controller, "get_state", _get_state)
    monkeypatch.setattr("app.session_state.get_state", _get_state)
    monkeypatch.setattr(flow_controller, "get_pending_prompt", lambda _: state.get("pending_prompt"))
    monkeypatch.setattr(flow_controller, "set_pending_prompt", _set_pending)
    monkeypatch.setattr(flow_controller, "push_pending_prompt", _push_pending)
    monkeypatch.setattr(flow_controller, "pop_pending_prompt", _pop_pending)
    monkeypatch.setattr(flow_controller, "save_chat_db", lambda *_: None)
    monkeypatch.setattr(flow_controller, "resolve_faq_or_product_query", lambda msg: f"FAQ:{msg}")
    monkeypatch.setattr(flow_controller, "handle_more_products_question", lambda *_: ("continue", False))
    monkeypatch.setattr(flow_controller, "list_orcamento_items", lambda *_: [])
    monkeypatch.setattr(flow_controller, "handle_pending_qty", lambda *_: None)
    monkeypatch.setattr(flow_controller, "handle_checkout", lambda *_: (None, False))

    reply, _ = flow_controller.handle_message("vocês vendem cano?", "s1")
    assert "FAQ:voce" in reply.lower() or "faq" in reply.lower()
    assert "voltando ao que estavamos" in reply.lower()
    assert state.get("pending_prompt")  # restored

    # Respond with expected yes/no after resume
    reply2, _ = flow_controller.handle_message("sim", "s1")
    assert state.get("pending_prompt") is None
    assert reply2 == "continue"
