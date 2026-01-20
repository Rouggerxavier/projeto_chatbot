import pytest

from app.product_search import parse_choice_indices
from app.flows import consultive_investigation
from app.flows.consultive_investigation import continue_investigation
from app.session_state import patch_state, get_state, reset_consultive_context


def test_parse_choice_indices_understands_words():
    nums = parse_choice_indices("acho que a segunda opcao serve", max_n=4)
    assert nums == [2]

    nums = parse_choice_indices("quero a terceira ou quarta", max_n=5)
    assert nums == [3, 4]


def test_consultive_investigation_sets_last_suggestions(monkeypatch):
    session_id = "test_consultive_suggestions"
    reset_consultive_context(session_id)

    flow_len = len(consultive_investigation.INVESTIGATION_FLOWS["cimento"])

    patch_state(session_id, {
        "consultive_investigation": True,
        "consultive_product_hint": "cimento",
        "consultive_application": "reboco",
        "consultive_investigation_step": flow_len,  # pula direto para recomendacao
    })

    monkeypatch.setattr(
        "app.flows.consultive_investigation.db_find_best_products_with_constraints",
        lambda *args, **kwargs: [
            {"id": 1, "nome": "Cimento CP II"},
            {"id": 2, "nome": "Cimento CP III"},
        ],
    )
    monkeypatch.setattr(
        "app.flows.technical_recommendations.get_technical_recommendation",
        lambda ctx: {"reasoning": "r", "summary": "s"},
    )
    monkeypatch.setattr(
        "app.flows.technical_recommendations.format_recommendation_text",
        lambda rec, products, context=None: "ok",
    )
    monkeypatch.setattr(
        "app.search_utils.extract_catalog_constraints_from_consultive",
        lambda reasoning, product_hint, context: {},
    )

    reply = continue_investigation(session_id, "qualquer resposta")
    assert reply == "ok"

    st = get_state(session_id)
    assert st["last_suggestions"] == [
        {"id": 1, "nome": "Cimento CP II"},
        {"id": 2, "nome": "Cimento CP III"},
    ]
    assert st["last_hint"] == "cimento"
