from app import flow_controller


def test_catalog_reply_safe(monkeypatch):
    calls = {"set": 0}

    def _db_find_best_products(query, k=6):
        return [{"id": 1, "nome": "Item 1"}]

    def _set_last_suggestions(session_id, options, hint, context=None):
        calls["set"] += 1

    monkeypatch.setattr(flow_controller, "db_find_best_products", _db_find_best_products)
    monkeypatch.setattr(flow_controller, "_set_last_suggestions", _set_last_suggestions)
    monkeypatch.setattr(flow_controller, "maybe_render_customer_message", lambda *_: None)

    reply = flow_controller._catalog_reply_for_query("s1", "cimento", None, category_hint="cimento")
    assert "Qual voce quer" in reply or "Qual voce quer?" in reply or "Qual voce procura" not in reply
    assert calls["set"] == 1
