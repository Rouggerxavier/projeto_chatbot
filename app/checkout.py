import re
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from database import (
    SessionLocal,
    Cliente,
    Pedido,
    Orcamento,
    ItemOrcamento,
    PedidoChat,
)
from app.session_state import get_state, patch_state
from app.cart_service import get_open_orcamento, format_orcamento
from app.text_utils import norm

# Mercado Pago (opcional: se o módulo não existir, o checkout segue sem link)
try:
    from app.mercadopago_payments import create_checkout_preference, choose_best_payment_link
except Exception:  # pragma: no cover
    create_checkout_preference = None  # type: ignore
    choose_best_payment_link = None  # type: ignore


FINALIZE_INTENTS = [
    "finalizar",
    "fechar",
    "fechar pedido",
    "finalizar pedido",
    "fechar o pedido",
    "finalizar o pedido",
    "pode fechar",
    "pode finalizar",
    "confirmar",
]


def _is_finalize_intent(message: str) -> bool:
    t = norm(message or "")
    return any(x in t for x in FINALIZE_INTENTS)


def extract_phone(message: str) -> Optional[str]:
    t = message or ""
    digits = re.sub(r"\D", "", t)
    # telefone BR costuma ter 10-13 dígitos (com DDI)
    if 10 <= len(digits) <= 13:
        return digits
    return None


def extract_name(message: str) -> Optional[str]:
    raw = (message or "").strip()
    if not raw:
        return None

    # evita pegar "2", "50kg" etc.
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 6:
        return None

    # precisa ter pelo menos 1 letra
    if not re.search(r"[A-Za-zÀ-ÿ]", raw):
        return None

    if len(raw) > 40:
        return None

    cleaned = re.sub(r"[^A-Za-zÀ-ÿ\s']", " ", raw).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    if len(cleaned) < 2:
        return None
    return cleaned


def ready_to_checkout(session_id: str) -> bool:
    st = get_state(session_id)

    orc = get_open_orcamento(session_id)
    if not orc:
        return False

    if not st.get("preferencia_entrega"):
        return False
    if not st.get("forma_pagamento"):
        return False

    # se entrega, exige endereço
    if st.get("preferencia_entrega") == "entrega":
        if not st.get("endereco"):
            return False

    # exige nome e telefone
    if not st.get("cliente_nome"):
        return False
    if not st.get("cliente_telefone"):
        return False

    return True


def _summary_from_orcamento_items(items: List[ItemOrcamento]) -> Tuple[str, float]:
    total = 0.0
    linhas = []
    for it in items:
        produto = it.produto
        if not produto:
            continue
        qtd = float(it.quantidade)
        vu = float(it.valor_unitario)
        sub = float(it.subtotal)
        total += sub
        linhas.append(f"{qtd:.0f} x {produto.nome} (R$ {vu:.2f} cada) = R$ {sub:.2f}")
    linhas.append(f"Total aproximado: R$ {total:.2f}")
    return "\n".join(linhas), total


def _create_pedido_from_orcamento(session_id: str) -> Tuple[Optional[int], Optional[str]]:
    st = get_state(session_id)

    db: Session = SessionLocal()
    try:
        orc: Optional[Orcamento] = (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
        if not orc:
            return None, "Não encontrei um orçamento aberto para finalizar."

        items = (
            db.query(ItemOrcamento)
            .filter(ItemOrcamento.id_orcamento == orc.id)
            .all()
        )
        if not items:
            return None, "Seu orçamento está vazio — adicione algum item antes de finalizar."

        resumo, total = _summary_from_orcamento_items(items)

        telefone = st.get("cliente_telefone") or ""
        nome = st.get("cliente_nome") or "Cliente do chat"

        cliente = db.query(Cliente).filter(Cliente.telefone == telefone).first()
        if not cliente:
            cliente = Cliente(nome=nome, telefone=telefone)
            db.add(cliente)
            db.flush()

        forma_pagamento = st.get("forma_pagamento") or ""
        preferencia_entrega = st.get("preferencia_entrega") or ""
        endereco = st.get("endereco") or ""

        pedido = Pedido(
            id_cliente=cliente.id,
            status="novo",
            needs_human=True,
        )
        db.add(pedido)
        db.flush()

        pedido_chat = PedidoChat(
            id_pedido=pedido.id,
            id_orcamento=orc.id,
            forma_pagamento=forma_pagamento,
            preferencia_entrega=preferencia_entrega,
            endereco=endereco,
            itens_json=[
                {
                    "id_produto": it.id_produto,
                    "quantidade": float(it.quantidade),
                    "valor_unitario": float(it.valor_unitario),
                    "subtotal": float(it.subtotal),
                }
                for it in items
            ],
            total=float(total),
            resumo=resumo,
        )
        db.add(pedido_chat)

        # fecha orçamento
        orc.status = "fechado"

        db.commit()

        patch_state(session_id, {
            "last_order_id": pedido.id,
            "last_order_summary": resumo,
            "last_order_total": total,
            "checkout_mode": False,
        })

        return pedido.id, None

    except Exception:
        db.rollback()
        return None, "Tive um problema ao finalizar o pedido. Um atendente humano pode revisar."
    finally:
        db.close()


def handle_checkout(message: str, session_id: str) -> Tuple[Optional[str], bool]:
    """
    Retorna (reply, needs_human). Se reply=None, fluxo segue normal.
    """
    st = get_state(session_id)

    if _is_finalize_intent(message):
        patch_state(session_id, {"checkout_mode": True})

    st = get_state(session_id)
    if not st.get("checkout_mode"):
        return None, False

    if not ready_to_checkout(session_id):
        resumo = format_orcamento(session_id)

        faltas = []
        if not st.get("preferencia_entrega"):
            faltas.append("• Você prefere **entrega** ou **retirada**?")
        if not st.get("forma_pagamento"):
            faltas.append("• A forma de pagamento é **pix**, **cartão** ou **dinheiro**?")
        if st.get("preferencia_entrega") == "entrega" and not st.get("endereco"):
            faltas.append("• Me passe o **endereço** (rua, número e bairro/CEP).")
        if not st.get("cliente_nome"):
            faltas.append("• Qual seu **nome**?")
        if not st.get("cliente_telefone"):
            faltas.append("• Qual seu **telefone** (com DDD)?")

        if faltas:
            return (
                "Para finalizar, preciso de mais algumas informações:\n"
                + "\n".join(faltas)
                + "\n\n"
                + "Resumo do orçamento atual:\n"
                + resumo,
                True,
            )

        return None, False

    # coleta nome/telefone se ainda faltou
    if not st.get("cliente_nome"):
        nm = extract_name(message)
        if nm:
            patch_state(session_id, {"cliente_nome": nm})
            return "Perfeito. Agora me informe seu **telefone** (com DDD).", True
        return "Qual seu **nome**?", True

    if not st.get("cliente_telefone"):
        ph = extract_phone(message)
        if ph:
            patch_state(session_id, {"cliente_telefone": ph})
            return "Obrigado! Agora confirme: deseja **finalizar** o pedido?", True
        return "Qual seu **telefone** (com DDD)?", True

    # cria pedido
    pedido_id, err = _create_pedido_from_orcamento(session_id)
    if err:
        return err, True
    if not pedido_id:
        return "Não consegui finalizar agora. Um atendente pode revisar.", True

    st = get_state(session_id)
    resumo = st.get("last_order_summary") or "(não consegui montar o resumo agora, mas o pedido foi registrado)"

    # Se houver Mercado Pago configurado, gera um link de pagamento para anexar na mensagem final
    payment_block = ""
    forma = (st.get("forma_pagamento") or "").strip().lower()
    total = float(st.get("last_order_total") or 0.0)
    if create_checkout_preference and total > 0 and forma in {"pix", "cartão", "cartao"}:
        try:
            pref = create_checkout_preference(pedido_id=int(pedido_id), total=float(total))
            link = (
                choose_best_payment_link(pref)
                if choose_best_payment_link
                else (pref.get("init_point") or pref.get("sandbox_init_point"))
            )
            if link:
                if forma == "pix":
                    payment_block = f"\n\n📲 Para pagar no **PIX**, use este link:\n{link}"
                else:
                    payment_block = f"\n\n💳 Para pagar no **cartão**, use este link:\n{link}"
        except Exception:
            payment_block = ""

    reply = (
        f"✅ Pedido **#{pedido_id}** registrado e encaminhado para um atendente finalizar.\n\n"
        f"Resumo do pedido:\n{resumo}"
        f"{payment_block}\n\n"
        "Um atendente humano vai revisar e finalizar seu pedido agora. 🙋‍♂️\n\n"
        "Obs.: esse orçamento foi **fechado** (por isso um novo orçamento pode ficar vazio). "
        "Se quiser fazer um novo pedido, é só me dizer os itens."
    )
    return reply, True
