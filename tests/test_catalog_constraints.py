from app.search_utils import extract_catalog_constraints_from_consultive


def test_extract_cp_variants():
    out = extract_catalog_constraints_from_consultive(
        "Recomendo CPIV para maior durabilidade.",
        "cimento",
        {},
    )
    assert out["category_hint"] == "cimento"
    assert "cp iv" in out["must_terms"]


def test_extract_cp3_variant():
    out = extract_catalog_constraints_from_consultive(
        "Use CP3 em laje externa.",
        "cimento",
        {},
    )
    assert "cp iii" in out["must_terms"]


def test_extract_tijolo_8_furos():
    out = extract_catalog_constraints_from_consultive(
        "Para muro, tijolo 8 furos atende bem.",
        "tijolo",
        {},
    )
    assert "8 furos" in out["must_terms"]


def test_extract_should_terms_from_context():
    out = extract_catalog_constraints_from_consultive(
        "Recomendacao tecnica.",
        "cimento",
        {"environment": "externa", "application": "laje"},
    )
    assert "externa" in out["should_terms"]
    assert "laje" in out["should_terms"]
