from typing import Optional, Tuple

from app.session_state import get_state, patch_state
from app.cart_service import get_open_orcamento, format_orcamento
from app.text_utils import norm

from .extractors import (
    extract_phone,
    extract_delivery_preference,
    extract_payment_method,
    extract_name,
    extract_email,
)
from .validators import is_finalize_intent, ready_to_checkout
from .order_creation import create_pedido_from_orcamento
from .payment_handling import generate_payment_block


def handle_more_products_question(message: str, session_id: str) -> Tuple[Optional[str], bool]:
    """
    Processa resposta para "Quer adicionar outro produto?"
    Retorna (reply, needs_human). Se reply=None, fluxo segue normal.
    """
    st = get_state(session_id)
    if not st.get("asking_for_more"):
        return None, False

    t = norm(message or "").strip().lower()
    
    if t in {"sim", "s", "yeah", "claro", "pode", "ok", "certo", "yes"}:
        patch_state(session_id, {"asking_for_more": False})
        return "Ótimo! Qual produto você quer adicionar?", False
    
    if t in {"não", "nao", "n", "no", "nope"}:
        patch_state(session_id, {
            "asking_for_more": False,
        })
        
        orc = get_open_orcamento(session_id)
        if not orc:
            return "Seu orçamento está vazio. Preciso que você adicione algo antes.", True
        
        st = get_state(session_id)  # Atualiza estado após limpar forma_pagamento
        resumo = format_orcamento(session_id)
        faltas = []
        if not st.get("preferencia_entrega"):
            faltas.append("• Você prefere **entrega** ou **retirada**?")
        if not st.get("forma_pagamento"):
            faltas.append("• A forma de pagamento é **pix**, **cartão** ou **dinheiro**?")
        if st.get("preferencia_entrega") == "entrega" and not st.get("endereco"):
            faltas.append("• Me passe o **endereço completo** (rua e número; bairro se souber).")
        if not st.get("cliente_email"):
            faltas.append("• Qual seu **e-mail**?")
        if not st.get("cliente_nome"):
            faltas.append("• Qual seu **nome**?")
        if not st.get("cliente_telefone"):
            faltas.append("• Qual seu **telefone** (com DDD)?")
        
        if faltas:
            patch_state(session_id, {"checkout_mode": True})
            return (
                "Ótimo! Agora preciso de alguns dados para finalizar:\n"
                + "\n".join(faltas)
                + "\n\n"
                + "Resumo:\n"
                + resumo,
                True,
            )
        else:
            patch_state(session_id, {"checkout_mode": True})
            return "Perfeito! Seus dados estão completos. Vou criar o pedido...", True
    
    return "Entendi. Você quer adicionar outro produto? (responda **sim** ou **não**)", True


def handle_checkout(message: str, session_id: str) -> Tuple[Optional[str], bool]:
    """
    Retorna (reply, needs_human). Se reply=None, fluxo segue normal.
    Coleta preferências → nome → telefone → cria pedido.
    """
    st = get_state(session_id)

    if is_finalize_intent(message):
        patch_state(session_id, {"checkout_mode": True})

    st = get_state(session_id)
    if not st.get("checkout_mode"):
        return None, False

    resumo = format_orcamento(session_id)

    # 1) Coleta preferência de entrega
    if not st.get("preferencia_entrega"):
        entrega = extract_delivery_preference(message)
        if entrega:
            patch_state(session_id, {"preferencia_entrega": entrega})
            st = get_state(session_id)

    # 2) Coleta endereço se necessário
    if st.get("preferencia_entrega") == "entrega" and not st.get("endereco"):
        from app.preferences import maybe_register_address
        maybe_register_address(message, session_id)
        st = get_state(session_id)

    # 3) Coleta forma de pagamento
    if not st.get("forma_pagamento"):
        pagamento = extract_payment_method(message)
        if pagamento:
            patch_state(session_id, {"forma_pagamento": pagamento})
            st = get_state(session_id)

    # 4) Coleta email
    if not st.get("cliente_email"):
        email = extract_email(message)
        if email:
            patch_state(session_id, {"cliente_email": email})
            st = get_state(session_id)

    # 5) Coleta nome
    if not st.get("cliente_nome"):
        nm = extract_name(message)
        if nm:
            patch_state(session_id, {"cliente_nome": nm})
            st = get_state(session_id)

    # 6) Coleta telefone
    if not st.get("cliente_telefone"):
        ph = extract_phone(message)
        if ph:
            patch_state(session_id, {"cliente_telefone": ph})
            st = get_state(session_id)

    # Verifica o que ainda falta
    faltas = []
    if not st.get("preferencia_entrega"):
        faltas.append("• Você prefere **entrega** ou **retirada**?")
    if not st.get("forma_pagamento"):
        faltas.append("• A forma de pagamento é **pix**, **cartão** ou **dinheiro**?")
    if st.get("preferencia_entrega") == "entrega" and not st.get("endereco"):
        faltas.append("• Me passe o **endereço completo** (rua e número; bairro se souber).")
    if not st.get("cliente_email"):
        faltas.append("• Qual seu **e-mail**?")
    if not st.get("cliente_nome"):
        faltas.append("• Qual seu **nome**?")
    if not st.get("cliente_telefone"):
        faltas.append("• Qual seu **telefone** (com DDD)?")

    if faltas:
        return (
            "Para finalizar o pedido, preciso dos seguintes dados:\n"
            + "\n".join(faltas)
            + "\n\n"
            + "Resumo:\n"
            + resumo,
            True,
        )

    # Captura forma_pagamento ANTES de criar pedido (order_creation limpa estado)
    forma_pagamento_backup = st.get("forma_pagamento")
    cliente_email_backup = st.get("cliente_email")
    cliente_nome_backup = st.get("cliente_nome")

    # Todos os dados coletados - cria pedido
    pedido_id, err = create_pedido_from_orcamento(session_id)
    if err:
        return err, True
    if not pedido_id:
        return "Não consegui finalizar agora. Um atendente pode revisar.", True

    st = get_state(session_id)
    resumo = st.get("last_order_summary") or "(não consegui montar o resumo agora, mas o pedido foi registrado)"

    # Gera bloco de pagamento (usa valores capturados ANTES do clear)
    forma = (forma_pagamento_backup or "").strip().lower()
    total = float(st.get("last_order_total") or 0.0)
    cliente_email = cliente_email_backup
    cliente_nome = cliente_nome_backup

    if not forma:
        print(f"❌ ERRO CRÍTICO: forma_pagamento vazia ao gerar pagamento. pedido={pedido_id}")
        raise RuntimeError(f"forma_pagamento vazia para pedido {pedido_id}")

    print(f"🔍 DEBUG payment generation: pedido={pedido_id}, forma='{forma}', total={total}, email='{cliente_email}'")

    payment_block = generate_payment_block(
        pedido_id=pedido_id,
        forma=forma,
        total=total,
        cliente_email=cliente_email,
        cliente_nome=cliente_nome,
    )

    print(f"🔍 DEBUG payment_block result (length={len(payment_block)}): {payment_block[:200] if payment_block else '(empty)'}")

    reply = (
        f"Pedido **#{pedido_id}** registrado e encaminhado para um atendente finalizar.\n\n"
        f"Resumo do pedido:\n{resumo}"
        f"{payment_block}\n\n"
        "Um atendente humano vai revisar e finalizar seu pedido agora.\n\n"
        "Obs.: esse orcamento foi **fechado** (por isso um novo orcamento pode ficar vazio). "
        "Se quiser fazer um novo pedido, e so me dizer os itens."
    )
    return reply, True
