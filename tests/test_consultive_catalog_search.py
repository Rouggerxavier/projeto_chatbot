from app import flow_controller


def test_search_consultive_exact_match(monkeypatch):
    calls = []

    def _extract(summary, hint, ctx):
        return {
            "category_hint": "cimento",
            "must_terms": ["cp iii"],
            "should_terms": ["externa"],
            "strict": True,
        }

    def _search(query, k=6, category_hint=None, must_terms=None, should_terms=None, strict=False):
        calls.append(
            {
                "category_hint": category_hint,
                "must_terms": must_terms,
                "should_terms": should_terms,
                "strict": strict,
            }
        )
        if strict:
            return [{"id": 1, "nome": "Cimento CP III", "preco": 30.0, "unidade": "UN", "estoque": 10}]
        return []

    monkeypatch.setattr(flow_controller, "extract_catalog_constraints_from_consultive", _extract)
    monkeypatch.setattr(flow_controller, "db_find_best_products_with_constraints", _search)
    result = flow_controller._search_consultive_catalog(
        product_hint="cimento",
        summary_text="Recomendo CP III.",
        known_context={"environment": "externa"},
        query_base="cimento",
    )
    assert result["exact_match_found"] is True
    assert result["items"]
    assert result["warning_text"] is None
    assert calls and calls[0]["strict"] is True


def test_search_consultive_fallback_warning(monkeypatch):
    def _extract(summary, hint, ctx):
        return {
            "category_hint": "cimento",
            "must_terms": ["cp iv"],
            "should_terms": [],
            "strict": True,
        }

    def _search(query, k=6, category_hint=None, must_terms=None, should_terms=None, strict=False):
        if strict:
            return []
        return [{"id": 2, "nome": "Cimento CP II", "preco": 25.0, "unidade": "UN", "estoque": 8}]

    monkeypatch.setattr(flow_controller, "extract_catalog_constraints_from_consultive", _extract)
    monkeypatch.setattr(flow_controller, "db_find_best_products_with_constraints", _search)
    result = flow_controller._search_consultive_catalog(
        product_hint="cimento",
        summary_text="Recomendo CP IV.",
        known_context={},
        query_base="cimento",
    )
    assert result["exact_match_found"] is False
    assert result["unavailable_specs"] == ["cp iv"]
    assert result["warning_text"]
    assert result["items"]
