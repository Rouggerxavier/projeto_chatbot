import re
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from database import SessionLocal, Cliente, Pedido, Orcamento, ItemOrcamento
from app.session_state import get_state, patch_state
from app.cart_service import get_open_orcamento, format_orcamento
from app.text_utils import norm


FINALIZE_TRIGGERS = [
    "finalizar",
    "finalizar pedido",
    "fechar pedido",
    "fechar o pedido",
    "finalizar o pedido",
    "pode finalizar",
    "pode fechar",
    "quero finalizar",
    "quero fechar",
]


def _is_finalize_intent(message: str) -> bool:
    t = norm(message)
    t = t.strip()
    return any(g == t or g in t for g in FINALIZE_TRIGGERS)


def _extract_phone(message: str) -> Optional[str]:
    m = re.search(r"(\d[\d\s\-().]{7,})", message or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    if len(digits) < 8:
        return None
    return digits


def _extract_name(message: str) -> Optional[str]:
    msg = (message or "").strip()
    pats = [
        r"me chamo ([A-Za-zÀ-ÿ\s]+)",
        r"meu nome é ([A-Za-zÀ-ÿ\s]+)",
        r"meu nome eh ([A-Za-zÀ-ÿ\s]+)",
        r"sou ([A-Za-zÀ-ÿ\s]+)",
    ]
    for pat in pats:
        m = re.search(pat, msg, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().strip(".!,")
    return None


def _maybe_free_text_name(message: str) -> Optional[str]:
    """
    Aceita nome “cru” quando estamos em checkout e faltando nome:
    - curto
    - contém letras
    - não parece comando (“finalizar”, “ok”, etc.)
    """
    raw = (message or "").strip()
    if not raw:
        return None

    t = norm(raw)

    # evita pegar palavras de fluxo como nome
    if t in {"ok", "certo", "beleza", "finalizar", "fechar", "entrega", "retirada", "pix", "cartao", "cartão", "dinheiro"}:
        return None

    # se tem dígitos demais, provavelmente é telefone/endereço
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 6:
        return None

    # precisa ter letra
    if not re.search(r"[A-Za-zÀ-ÿ]", raw):
        return None

    # tamanho razoável
    if len(raw) > 40:
        return None

    # remove caracteres esquisitos
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

    if st.get("preferencia_entrega") == "entrega":
        if not (st.get("bairro") or st.get("cep") or st.get("endereco")):
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

        resumo, _total = _summary_from_orcamento_items(items)

        telefone = st.get("cliente_telefone") or ""
        nome = st.get("cliente_nome") or "Cliente do chat"

        cliente = db.query(Cliente).filter(Cliente.telefone == telefone).first()
        if not cliente:
            cliente = Cliente(nome=nome, telefone=telefone)
            db.add(cliente)
            db.flush()
        else:
            if nome and (not cliente.nome or cliente.nome.strip() == "Cliente do chat"):
                cliente.nome = nome

        observacoes = []
        observacoes.append("Origem: chatbot")
        observacoes.append(f"Entrega/retirada: {st.get('preferencia_entrega')}")
        observacoes.append(f"Pagamento: {st.get('forma_pagamento')}")
        if st.get("bairro"):
            observacoes.append(f"Bairro: {st.get('bairro')}")
        if st.get("cep"):
            observacoes.append(f"CEP: {st.get('cep')}")
        if st.get("endereco"):
            observacoes.append(f"Endereço: {st.get('endereco')}")

        pedido = Pedido(
            id_cliente=cliente.id,
            status="aberto",
            observacoes="\n".join(observacoes),
        )
        db.add(pedido)
        db.flush()

        # fecha orçamento (não apaga)
        orc.status = "fechado"
        db.commit()

        patch_state(session_id, {
            "last_order_id": pedido.id,
            "last_order_summary": resumo,
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

    # entra em modo checkout somente se o usuário pedir
    if _is_finalize_intent(message):
        patch_state(session_id, {"checkout_mode": True})

    st = get_state(session_id)
    if not st.get("checkout_mode"):
        return None, False

    # se não está pronto, pede só o que falta
    if not ready_to_checkout(session_id):
        resumo = format_orcamento(session_id)

        faltas = []
        if not st.get("preferencia_entrega"):
            faltas.append("**entrega** ou **retirada**")
        if not st.get("forma_pagamento"):
            faltas.append("forma de pagamento (**PIX**, **cartão** ou **dinheiro**)")
        if st.get("preferencia_entrega") == "entrega":
            if not (st.get("bairro") or st.get("cep") or st.get("endereco")):
                faltas.append("**bairro** ou **CEP/endereço** para entrega")

        return (f"{resumo}\n\nPara finalizar, preciso de: " + ", ".join(faltas) + ".", False)

    # captura nome/telefone
    nome = _extract_name(message)
    if not nome and not st.get("cliente_nome"):
        # ✅ aceita nome “cru”
        nome = _maybe_free_text_name(message)

    if nome:
        patch_state(session_id, {"cliente_nome": nome})

    tel = _extract_phone(message)
    if tel:
        patch_state(session_id, {"cliente_telefone": tel})

    st = get_state(session_id)

    if not st.get("cliente_nome"):
        return "Para eu encaminhar ao atendente, me diga seu **nome** (ex.: “me chamo João” ou apenas “João”).", False
    if not st.get("cliente_telefone"):
        return "Agora me informe seu **telefone** para contato (ex.: 83999999999).", False

    # cria pedido
    pedido_id, err = _create_pedido_from_orcamento(session_id)
    if err:
        return err, True

    # ✅ pega o estado ATUALIZADO (antes era isso que deixava o resumo vazio)
    st = get_state(session_id)
    resumo = st.get("last_order_summary") or "(não consegui montar o resumo agora, mas o pedido foi registrado)"

    reply = (
        f"✅ Pedido **#{pedido_id}** registrado e encaminhado para um atendente finalizar.\n\n"
        f"Resumo do pedido:\n{resumo}\n\n"
        "Um atendente humano vai revisar e finalizar seu pedido agora. 🙋‍♂️\n\n"
        "Obs.: esse orçamento foi **fechado** (por isso um novo orçamento pode ficar vazio). "
        "Se quiser fazer um novo pedido, é só me dizer os itens."
    )
    return reply, True
