from typing import Dict, Any

from app import flow_controller
from app.flows import usage_context


def test_numeric_selection_after_usage_context(monkeypatch):
    state: Dict[str, Any] = {
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
    }

    # Patch state helpers
    def _patch_state(_, updates):
        state.update(updates)
        return state

    monkeypatch.setattr(usage_context, "patch_state", _patch_state)
    monkeypatch.setattr(usage_context, "get_state", lambda *_: state)
    monkeypatch.setattr("app.session_state.patch_state", _patch_state)
    monkeypatch.setattr("app.session_state.get_state", lambda *_: state)

    # Produtos simulados
    products = [
        {"id": 1, "nome": "Produto 1"},
        {"id": 2, "nome": "Produto 2"},
        {"id": 3, "nome": "Produto 3"},
    ]
    monkeypatch.setattr(usage_context, "db_find_best_products", lambda *args, **kwargs: products)
    monkeypatch.setattr("app.flows.consultive_investigation.start_investigation", lambda *_: None)

    # Executa fluxo que popula last_suggestions
    usage_context.start_usage_context_flow("s1", "cimento", "laje")
    assert state.get("last_suggestions")
    assert state["last_suggestions"][1]["id"] == 2

    # Agora testa selecao numerica no handle_message
    def _get_state(_):
        return state

    class _FakeProd:
        def __init__(self, pid):
            self.id = pid
            self.nome = f"Produto {pid}"
            self.preco = 10.0
            self.estoque_atual = 5
            self.unidade = "UN"

    def _db_get_product_by_id(pid):
        return _FakeProd(pid)

    def _set_pending_for_qty(session_id, produto, requested_kg=None):
        return f"qty-set-{produto.id}"

    monkeypatch.setattr(flow_controller, "get_state", _get_state)
    monkeypatch.setattr(flow_controller, "patch_state", _patch_state)
    monkeypatch.setattr(flow_controller, "save_chat_db", lambda *_: None)
    monkeypatch.setattr(flow_controller, "route_intent", lambda *_: None)
    monkeypatch.setattr(flow_controller, "list_orcamento_items", lambda *_: [])
    monkeypatch.setattr(flow_controller, "db_get_product_by_id", _db_get_product_by_id)
    monkeypatch.setattr("app.product_search.db_get_product_by_id", _db_get_product_by_id)
    monkeypatch.setattr("app.flows.product_selection.get_state", _get_state)
    monkeypatch.setattr("app.flows.product_selection.patch_state", _patch_state)
    monkeypatch.setattr("app.flows.product_selection.db_get_product_by_id", _db_get_product_by_id)
    monkeypatch.setattr("app.flows.product_selection.set_pending_for_qty", _set_pending_for_qty)
    monkeypatch.setattr(flow_controller, "handle_more_products_question", lambda *_: (None, False))
    monkeypatch.setattr(flow_controller, "handle_pending_qty", lambda *_: None)
    monkeypatch.setattr(flow_controller, "handle_checkout", lambda *_: (None, False))

    reply, _ = flow_controller.handle_message("2", "s1")
    assert reply == "qty-set-2"
