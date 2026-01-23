from app.nlu.expected_parser import parse_expected_field
from app.conversation import policy


def test_expected_bitola_consumes_number():
    out = parse_expected_field("bitola", "50")
    assert out == "50mm"


def test_expected_bitola_consumes_number_with_unit():
    out = parse_expected_field("bitola", "50mm")
    assert out == "50mm"


def test_expected_qty_consumes_number():
    out = parse_expected_field("quantidade", "15")
    assert out == "15"


def test_expected_qty_consumes_word_number():
    out = parse_expected_field("quantidade", "quinze")
    assert out == "15"


def test_policy_does_not_repeat_after_consumed_qty(monkeypatch):
    # Simula fluxo: required preenchidos e quantidade consumida -> nao deve perguntar qty de novo
    attrs = {"item": "joelho", "material": "pvc", "sistema_uso": "esgoto", "diametro": "50mm", "quantidade": "15"}
    action = policy.next_action("tubos_conexoes", attrs, {}, [])
    assert action["action"] != "ask_qty"
