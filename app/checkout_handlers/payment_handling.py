from typing import Optional

from app.mercadopago_payments import _validate_email, create_pix_payment, create_checkout_preference


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

    # Se nao tem email valido, nao tenta gerar pagamento online
    if not cliente_email or "@" not in cliente_email:
        return ""

    try:
        _validate_email(cliente_email)
    except ValueError:
        return ""

    try:
        if forma_lower == "pix":
            print(f"Gerando pagamento PIX para pedido #{pedido_id}, total=R$ {total}")

            pix_result = create_pix_payment(
                pedido_id=pedido_id,
                total=total,
                payer_email=cliente_email,
                payer_first_name=cliente_nome.split()[0] if cliente_nome else "Cliente",
                payer_last_name=" ".join(cliente_nome.split()[1:]) if " " in cliente_nome else "",
                description=f"Pedido #{pedido_id} (PIX)",
            )

            qr_code = pix_result.get("qr_code") or pix_result.get("copy_and_paste")
            status = pix_result.get("status", "pendente")

            if status == "pending" and qr_code:
                return (
                    f"\n\n**Pagamento PIX:**\n"
                    f"```\n{qr_code}\n```\n"
                    f"Copie o codigo acima para pagar."
                )
            return ""

        elif forma_lower in ("cartao", "cartão"):
            print(f"Gerando Checkout para pedido #{pedido_id}, total=R$ {total}")

            checkout_result = create_checkout_preference(
                pedido_id=pedido_id,
                total=total,
                payer_email=cliente_email,
                title=f"Pedido #{pedido_id}",
            )

            payment_link = checkout_result.get("sandbox_init_point") or checkout_result.get("init_point")

            if payment_link:
                return f"\n\n**Link de pagamento:** {payment_link}"
            return ""

        else:
            return ""

    except Exception as e:
        import traceback
        print(f"Erro ao gerar pagamento: {str(e)}")
        traceback.print_exc()
        return ""


