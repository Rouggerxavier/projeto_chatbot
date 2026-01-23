import pytest

from app import conversation_engine as ce


def test_no_repeat_sistema_quando_ja_preenchido():
    slots = {"item": "joelho", "material": "pvc", "sistema_uso": "esgoto"}
    action = ce.next_step("buy", slots, ["sistema_uso"])
    assert action["slot"] != "sistema_uso"


def test_pergunta_bitola_quando_slots_principais_preenchidos():
    slots = {"item": "joelho", "material": "pvc", "sistema_uso": "esgoto", "angulo": "45"}
    action = ce.next_step("buy", slots, [])
    assert action["slot"] == "diametro"
    assert "bitola" in action["question"].lower()


def test_apenas_joelho_nao_gatilha_loop_item():
    slots = ce.extract_slots("apenas o joelho pvc 45 esgoto", {})
    action = ce.next_step("buy", slots, [])
    assert action["slot"] != "item"


def test_resposta_parede_repergunta_sistema():
    slots = ce.extract_slots("parede", {})
    action = ce.next_step("buy", slots, ["sistema_uso"])
    assert action["slot"] == "sistema_uso"


def test_quando_slots_completos_pede_quantidade():
    slots = {"item": "joelho", "material": "pvc", "sistema_uso": "esgoto", "angulo": "45", "diametro": "50mm"}
    action = ce.next_step("buy", slots, [])
    assert action["action"] == "ask_qty"
    assert "quantas" in action["question"].lower()
