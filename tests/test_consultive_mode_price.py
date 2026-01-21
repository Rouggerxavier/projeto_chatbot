from app import consultive_mode


def test_comparison_with_valid_prices():
    products = [
        {"nome": "Prod A", "preco": 120.0},
        {"nome": "Prod B", "preco": 80.0},
    ]
    resp = consultive_mode._answer_comparison_question(products, "qual a diferenca?")
    assert "custo maior" in resp.lower() or "preços similares" in resp.lower()


def test_comparison_with_invalid_prices():
    products = [
        {"nome": "Prod A", "preco": 0},
        {"nome": "Prod B", "preco": None},
    ]
    resp = consultive_mode._answer_comparison_question(products, "qual a diferenca?")
    assert "custo" not in resp.lower()
    assert "qual deles" in resp.lower()
