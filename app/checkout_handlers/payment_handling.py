from typing import Optional

from app.mercadopago_payments import _validate_email, create_checkout_preference


def generate_payment_block(
    pedido_id: int,
    forma: str,
    total: float,
    cliente_email: Optional[str] = None,
    cliente_nome: Optional[str] = None,
) -> str:
    """
    Gera bloco de texto com informacoes de pagamento.
    Retorna string vazia se forma de pagamento nao requer link/QR.

    NOTA: O pedido ja deve ter sido criado antes de chamar esta funcao.
    """
    if not pedido_id or total <= 0:
        return ""

    forma_lower = (forma or "").strip().lower()
    cliente_nome = cliente_nome or "Cliente"

    # Dinheiro nao precisa de link/QR
    if forma_lower == "dinheiro":
        return "\n\nPagamento: **dinheiro** (a combinar na entrega/retirada)"

    # Se nao tem email valido, nao tenta gerar pagamento online (exceto dinheiro)
    if not cliente_email or "@" not in cliente_email:
        if forma_lower in ("pix", "cartao"):
            print(f"⚠️ Email ausente ou inválido para pagamento online: {cliente_email}")
            return ""
        return ""

    try:
        _validate_email(cliente_email)
    except ValueError as e:
        print(f"⚠️ Validação de email falhou: {e}")
        return ""

    try:
        # Temporariamente ambos PIX e CARTAO usam Preference (checkout link)
        if forma_lower == "pix":
            print(f"📤 Gerando Checkout (PIX) para pedido #{pedido_id}, total=R$ {total}, email={cliente_email}")

            checkout_result = create_checkout_preference(
                pedido_id=pedido_id,
                total=total,
                payer_email=cliente_email,
                title=f"Pedido #{pedido_id} (PIX)",
            )

            print(f"📥 Resposta MP Checkout (PIX): {checkout_result}")

            payment_link = checkout_result.get("sandbox_init_point") or checkout_result.get("init_point")

            if payment_link:
                print(f"✅ Link gerado (PIX): {payment_link}")
                return f"\n\n**Link de pagamento (PIX):** {payment_link}"
            else:
                print(f"❌ Nenhum link retornado (PIX). Resposta completa: {checkout_result}")
                return ""

        elif forma_lower == "cartao":
            print(f"📤 Gerando Checkout para pedido #{pedido_id}, total=R$ {total}, email={cliente_email}")

            checkout_result = create_checkout_preference(
                pedido_id=pedido_id,
                total=total,
                payer_email=cliente_email,
                title=f"Pedido #{pedido_id}",
            )

            print(f"📥 Resposta MP Checkout: {checkout_result}")

            payment_link = checkout_result.get("sandbox_init_point") or checkout_result.get("init_point")

            if payment_link:
                print(f"✅ Link gerado: {payment_link}")
                return f"\n\n**Link de pagamento (cartão):** {payment_link}"
            else:
                print(f"❌ Nenhum link retornado. Resposta completa: {checkout_result}")
                return ""

        else:
            return ""

    except Exception as e:
        import traceback
        print(f"Erro ao gerar pagamento: {str(e)}")
        traceback.print_exc()
        return ""


