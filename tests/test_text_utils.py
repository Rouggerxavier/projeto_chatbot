import pytest

from app import text_utils
from app.guardrails import SAFE_NOTE, apply_guardrails


@pytest.mark.parametrize(
    "message,expected",
    [
        ("quero 3 sacos de cimento", True),
        ("tem areia 2m3?", True),
        ("vou pagar no pix e retirada", False),
        ("", False),
    ],
)
def test_has_product_intent(message, expected):
    assert text_utils.has_product_intent(message) is expected


def test_sanitize_reply_strips_forbidden_lines_and_adds_safe_note():
    reply = "Enviando código de rastreio para o seu e-mail.\nTudo certo!"

    cleaned = text_utils.sanitize_reply(reply)

    # linha proibida removida
    assert "enviando código de rastreio" not in cleaned.lower()
    assert "seu e-mail" not in cleaned.lower()
    # texto original permitido deve ser preservado
    assert "Tudo certo!" in cleaned
    assert SAFE_NOTE in cleaned


def test_apply_guardrails_preserves_clean_text():
    reply = "Pedido registrado com sucesso."

    cleaned, changed = apply_guardrails(reply)

    assert cleaned == reply
    assert changed is False
    # não deve anexar nota se nada foi alterado
    assert SAFE_NOTE not in cleaned

def test_sanitize_reply_preserves_mercadopago_link():
    reply = "Pague aqui:\nhttps://www.mercadopago.com.br/checkout/v1/redirect?pref_id=123"
    cleaned = text_utils.sanitize_reply(reply)
    assert "mercadopago.com.br" in cleaned.lower()
