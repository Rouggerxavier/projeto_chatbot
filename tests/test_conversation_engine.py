from app.catalog_schema import get_category_schema
from app.conversation import policy
from app.nlu import extractor
from app import catalog_schema


def test_policy_nao_repergunta_sistema_quando_preenchido():
    attrs = {"item": "tubo", "material": "pvc", "sistema_uso": "esgoto"}
    action = policy.next_action("tubos_conexoes", attrs, {"sistema_uso": 1}, [])
    assert action["slot"] != "sistema_uso"


def test_policy_escolhe_bitola_quando_basico_preenchido():
    attrs = {"item": "joelho", "material": "pvc", "sistema_uso": "esgoto", "angulo": "45"}
    action = policy.next_action("tubos_conexoes", attrs, {}, [])
    assert action["slot"] == "diametro"


def test_policy_info_gain_escolhe_atributo_mais_discriminante():
    attrs = {"item": "tubo", "material": "pvc", "sistema_uso": "agua_fria"}
    candidates = [
        {"attributes": {"diametro": "20", "material": "pvc"}},
        {"attributes": {"diametro": "50", "material": "pvc"}},
        {"attributes": {"diametro": "50", "material": "pvc"}},
    ]
    action = policy.next_action("tubos_conexoes", attrs, {}, candidates)
    assert action["slot"] == "diametro"


def test_extractor_entende_categoria_tubos():
    out = extractor.extract("quero joelho pvc 50mm esgoto", {}, catalog_schema.CATEGORY_SCHEMA)
    assert out["category_guess"] == "tubos_conexoes"
    assert out["attributes"].get("sistema_uso") == "esgoto"
    assert out["attributes"].get("diametro")


def test_extractor_entende_categoria_tintas():
    out = extractor.extract("tinta para parede externa base agua 18L", {}, catalog_schema.CATEGORY_SCHEMA)
    assert out["category_guess"] == "tintas"
    assert out["attributes"].get("base") == "agua"
    assert out["attributes"].get("ambiente") == "externa"
    assert out["attributes"].get("volume")


def test_policy_quando_required_preenchidos_pede_quantidade():
    attrs = {"item": "joelho", "material": "pvc", "sistema_uso": "esgoto", "diametro": "50mm"}
    action = policy.next_action("tubos_conexoes", attrs, {}, [])
    assert action["action"] == "ask_qty"
