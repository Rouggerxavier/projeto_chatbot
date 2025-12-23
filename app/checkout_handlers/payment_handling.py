from typing import Optional, Tuple
from .extractors import split_first_last

try:
    from app.mercadopago_payments import (
        create_checkout_preference,
        choose_best_payment_link,
        create_pix_payment,
    )
    print("✅ Módulo de pagamentos Mercado Pago carregado com sucesso")
except Exception as e:
    print(f"⚠️ Mercado Pago não disponível: {e}")
    create_checkout_preference = None
    choose_best_payment_link = None
    create_pix_payment = None


def generate_payment_block(
    pedido_id: int,
    forma: str,
    total: float,
    cliente_email: Optional[str],
    cliente_nome: Optional[str],
) -> str:
    """Gera o bloco de pagamento (PIX ou cartão) para anexar na mensagem final."""
    payment_block = ""
    first_name, last_name = split_first_last(cliente_nome)
    metadata = {"pedido_id": int(pedido_id), "forma_pagamento": forma} if pedido_id else None
    
    print(f"💳 Verificando pagamento: forma={forma!r}, total={total}, create_pix_payment={create_pix_payment is not None}, create_checkout_preference={create_checkout_preference is not None}")

    # PIX via create_pix_payment
    if total > 0 and forma == "pix" and create_pix_payment:
        try:
            print(f"🔄 Gerando pagamento PIX para pedido #{pedido_id}, total=R$ {total}")
            pix_payment = create_pix_payment(
                pedido_id=int(pedido_id),
                total=float(total),
                payer_email=cliente_email,
                payer_first_name=first_name,
                payer_last_name=last_name,
                metadata=metadata,
            )
            qr_code = pix_payment.get("qr_code") or pix_payment.get("copy_and_paste")
            ticket_url = pix_payment.get("ticket_url")
            block_parts = []
            if qr_code:
                block_parts.append(f"📲 Para pagar no **PIX**, copie e cole o código:\n{qr_code}")
            if ticket_url:
                block_parts.append(f"Visualize o QR neste link:\n{ticket_url}")
            if block_parts:
                payment_block = "\n\n" + "\n\n".join(block_parts)
                print(f"✅ QR Code PIX gerado com sucesso")
            else:
                print(f"⚠️ Pagamento PIX criado mas sem QR code/ticket_url")
        except Exception as e:
            print(f"❌ Erro ao gerar pagamento PIX: {e}")
            import traceback
            traceback.print_exc()
            error_str = str(e).lower()
            if "401" in error_str or "unauthorized" in error_str:
                payment_block = "\n\n⚠️ Não foi possível gerar o QR Code PIX agora (credenciais de pagamento precisam ser atualizadas). Um atendente vai enviar o link de pagamento em breve."
            elif "connection" in error_str or "timeout" in error_str or "dns" in error_str or "resolve" in error_str:
                payment_block = "\n\n⚠️ Não foi possível gerar o QR Code PIX agora (problema de conexão). Um atendente vai enviar o link de pagamento em breve."
            else:
                payment_block = ""
    
    # PIX via Checkout Pro
    elif total > 0 and forma == "pix" and create_checkout_preference:
        try:
            print(f"🔄 Gerando link de checkout PIX para pedido #{pedido_id}, total=R$ {total}")
            pref = create_checkout_preference(
                pedido_id=int(pedido_id),
                total=float(total),
                payer_email=cliente_email,
                metadata=metadata,
            )
            link = (
                choose_best_payment_link(pref)
                if choose_best_payment_link
                else (pref.get("init_point") or pref.get("sandbox_init_point"))
            )
            if link:
                payment_block = f"\n\n📲 Para pagar no **PIX**, use este link:\n{link}"
                print(f"✅ Link de checkout PIX gerado: {link}")
            else:
                print(f"⚠️ Checkout preference criada mas sem link")
        except Exception as e:
            print(f"❌ Erro ao gerar checkout PIX: {e}")
            import traceback
            traceback.print_exc()
            error_str = str(e).lower()
            if "401" in error_str or "unauthorized" in error_str:
                payment_block = "\n\n⚠️ Não foi possível gerar o link de pagamento PIX agora (credenciais de pagamento precisam ser atualizadas). Um atendente vai enviar o link em breve."
            elif "connection" in error_str or "timeout" in error_str or "dns" in error_str or "resolve" in error_str:
                payment_block = "\n\n⚠️ Não foi possível gerar o link de pagamento PIX agora (problema de conexão). Um atendente vai enviar o link em breve."
            else:
                payment_block = ""
    
    # Cartão via Checkout Pro
    elif total > 0 and forma in {"cartão", "cartao"} and create_checkout_preference:
        try:
            print(f"🔄 Gerando link de checkout CARTÃO para pedido #{pedido_id}, total=R$ {total}")
            pref = create_checkout_preference(
                pedido_id=int(pedido_id),
                total=float(total),
                payer_email=cliente_email,
                metadata=metadata,
            )
            link = (
                choose_best_payment_link(pref)
                if choose_best_payment_link
                else (pref.get("init_point") or pref.get("sandbox_init_point"))
            )
            if link:
                payment_block = f"\n\n💳 Para pagar no **cartão**, use este link:\n{link}"
                print(f"✅ Link de checkout CARTÃO gerado: {link}")
            else:
                print(f"⚠️ Checkout preference criada mas sem link")
        except Exception as e:
            print(f"❌ Erro ao gerar checkout CARTÃO: {e}")
            import traceback
            traceback.print_exc()
            error_str = str(e).lower()
            if "401" in error_str or "unauthorized" in error_str:
                payment_block = "\n\n⚠️ Não foi possível gerar o link de pagamento com cartão agora (credenciais de pagamento precisam ser atualizadas). Um atendente vai enviar o link em breve."
            elif "connection" in error_str or "timeout" in error_str or "dns" in error_str or "resolve" in error_str:
                payment_block = "\n\n⚠️ Não foi possível gerar o link de pagamento com cartão agora (problema de conexão). Um atendente vai enviar o link em breve."
            else:
                payment_block = ""
    else:
        if forma in {"pix", "cartão", "cartao"}:
            print(f"⚠️ Pagamento {forma} não gerado - funções MP não disponíveis ou total={total}")

    return payment_block
