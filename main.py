from fastapi import FastAPI
from pydantic import BaseModel as PydanticBaseModel
from dotenv import load_dotenv
import os
from typing import Dict, Optional, Tuple, List, Any
import traceback
import re
from uuid import uuid4
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from langchain_core.tools import tool  # mantido só para padronizar funções/tools

from database import (
    SessionLocal,
    Produto,
    ChatHistory,
    Orcamento,
    ItemOrcamento,
    init_db,
)

# ============================
# Boot
# ============================

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY não encontrada. Verifique seu .env")
os.environ["GROQ_API_KEY"] = GROQ_API_KEY

app = FastAPI(title="Chatbot Materiais de Construção")


@app.on_event("startup")
def on_startup():
    init_db()


class ChatRequest(PydanticBaseModel):
    message: str
    user_id: Optional[str] = None


class ChatResponse(PydanticBaseModel):
    reply: str
    needs_human: bool = False
    session_id: str


# ============================
# Constantes
# ============================

HORARIO_LOJA = "Nosso horário é de segunda a sexta, 7h às 18h; sábado, 7h às 12h."
BAIRROS_ENTREGA = ["manaíra", "intermares", "aeroclube", "tambaú", "bessa"]
CEP_REGEX = re.compile(r"\b\d{5}-\d{3}\b")

FORBIDDEN_REPLY_PATTERNS = [
    r"código de rastreamento",
    r"rastreamento",
    r"você receberá um e-?mail",
    r"enviaremos um e-?mail",
    r"código de barras do seu pedido",
    r"código de referência",
    r"pedido foi enviado",
    r"pedido enviado",
    r"rastreio",
    r"tracking",
    r"será debitado do seu pix",
    r"debitar do pix",
    r"qr\s*code",
    r"qrcode",
    r"produto com o id",
    r"id \d+",
    r"por favor, aguarde",
]
FORBIDDEN_REPLY_REGEX = re.compile("|".join(FORBIDDEN_REPLY_PATTERNS), flags=re.IGNORECASE)

STOPWORDS = {
    "para", "pro", "pra", "com", "sem", "e", "ou",
    "da", "do", "de", "a", "o", "os", "as", "um", "uma",
    "no", "na", "nos", "nas", "por", "favor", "pf", "isso",
    "quero", "queria", "preciso", "gostaria", "me", "manda",
    "sim", "ok", "beleza", "certo", "confirmo", "confirmar",
    "tambem", "também", "tb"
}
UNITS_WORDS = {"kg", "quilo", "quilos", "saco", "sacos", "un", "unidade", "unidades", "m", "metro", "metros"}

GREETINGS = {"bom dia", "boa tarde", "boa noite", "oi", "olá", "ola", "e ai", "eai", "fala", "tudo bem"}
INTENT_KEYWORDS = [
    "quero", "queria", "preciso", "gostaria", "tem", "vende", "vcs tem", "vocês tem",
    "quanto custa", "preço", "valor", "orçamento", "orcamento", "comprar", "pedido",
]

CART_SHOW_KEYWORDS = [
    "meu orçamento", "meu orcamento", "ver orçamento", "ver orcamento",
    "resumo", "carrinho", "itens", "meu pedido",
    "ja fez o orçamento", "já fez o orçamento", "ja fez o orcamento", "já fez o orcamento",
    "mostra o orçamento", "mostrar o orçamento", "qual o total", "quanto deu", "quanto ficou"
]
CART_RESET_KEYWORDS = [
    "limpar orçamento", "limpar orcamento", "zerar orçamento", "zerar orcamento",
    "retirar tudo", "tirar tudo", "esvaziar carrinho", "começar do zero", "comecar do zero"
]


# ============================
# Estado de sessão
# ============================

session_state: Dict[str, Dict[str, Any]] = {}


def get_state(session_id: str) -> Dict[str, Any]:
    if session_id not in session_state:
        session_state[session_id] = {
            "preferencia_entrega": None,      # "entrega" / "retirada"
            "bairro": None,
            "endereco": None,
            "cep": None,
            "forma_pagamento": None,          # "pix" / "cartão" / "dinheiro"

            "last_suggestions": [],           # [{"id": int, "nome": str}, ...]
            "last_hint": None,
            "last_requested_kg": None,        # float do pedido original (ex.: 200)

            "pending_product_id": None,       # int
            "pending_suggested_units": None,  # float
            "awaiting_qty": False,            # bool

            # fila pra múltipla escolha (1 e 3)
            "selection_queue": [],            # [produto_id, produto_id, ...]

            "last_added_signature": None,
            "last_user_norm": None,
        }
    return session_state[session_id]


# ============================
# Normalização
# ============================

def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join([c for c in s if not unicodedata.combining(c)])


def _norm(s: str) -> str:
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("cpii", "cp ii").replace("cp2", "cp ii")
    s = s.replace("cpiii", "cp iii").replace("cp3", "cp iii")
    return s


def sanitize_reply(text: str) -> str:
    if not text:
        return text
    if not FORBIDDEN_REPLY_REGEX.search(text):
        return text
    kept = []
    for ln in text.splitlines():
        if FORBIDDEN_REPLY_REGEX.search(ln):
            continue
        kept.append(ln)
    cleaned = "\n".join(kept).strip()
    if not cleaned:
        cleaned = "Certo! Me diga qual produto e quantidade você quer."
    cleaned += "\n\nObs.: Eu não envio e-mail nem rastreio; eu apenas monto o orçamento/pedido aqui no chat."
    return cleaned


def is_greeting(message: str) -> bool:
    t = _norm(message)
    if t in GREETINGS:
        return True
    return any(t.startswith(g) and len(t) <= len(g) + 2 for g in GREETINGS)


def is_hours_question(message: str) -> bool:
    t = _norm(message)
    return any(k in t for k in ["horario", "hora", "funciona", "aberto", "fechado"])


def detect_delivery_bairro(message: str) -> Optional[str]:
    t = strip_accents((message or "").lower())
    if "entrega" not in t:
        return None
    for b in BAIRROS_ENTREGA:
        if strip_accents(b) in t:
            return b
    return None


def has_product_intent(message: str) -> bool:
    t = _norm(message)
    return any(k in t for k in INTENT_KEYWORDS)


def is_cart_show_request(message: str) -> bool:
    t = _norm(message)
    return any(k in t for k in CART_SHOW_KEYWORDS)


def is_cart_reset_request(message: str) -> bool:
    t = _norm(message)
    return any(k in t for k in CART_RESET_KEYWORDS)


def is_affirmative(message: str) -> bool:
    t = _norm(message)
    return t in {"sim", "isso", "ok", "certo", "confirmo", "confirmar", "pode", "manda", "pode sim"} or "confirm" in t


def message_is_preferences_only(message: str) -> bool:
    """
    True se a msg é basicamente "vai ser entrega", "pix", "retirada", etc.
    e NÃO parece pedido de produto.
    """
    t = _norm(message)
    has_pref = any(x in t for x in ["entrega", "retirada", "retirar", "pix", "dinheiro", "cartao", "credito", "debito"])
    if not has_pref:
        return False
    # se tem intenção de produto, não é "apenas preferência"
    if has_product_intent(message):
        return False
    # se tem número + kg ou nome, pode ser item
    if extract_kg_quantity(message) is not None or extract_units_quantity(message) is not None:
        return False
    return True


# ============================
# DB helpers: Orçamento
# ============================

def get_orcamento_aberto(db: Session, session_id: str) -> Orcamento:
    orc = (
        db.query(Orcamento)
        .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
        .first()
    )
    if not orc:
        orc = Orcamento(user_id=session_id, status="aberto", total_aproximado=0)
        db.add(orc)
        db.flush()
    return orc


def recompute_orcamento_total(db: Session, orc: Orcamento) -> None:
    itens = db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).all()
    total = 0.0
    for it in itens:
        total += float(it.subtotal)
    orc.total_aproximado = total
    db.flush()


def add_item_to_orcamento(session_id: str, produto: Produto, quantidade: float) -> Tuple[bool, str]:
    db: Session = SessionLocal()
    try:
        orc = get_orcamento_aberto(db, session_id)
        preco = float(produto.preco) if produto.preco is not None else 0.0
        subtotal_add = round(quantidade * preco, 2)

        item = (
            db.query(ItemOrcamento)
            .filter(ItemOrcamento.id_orcamento == orc.id, ItemOrcamento.id_produto == produto.id)
            .first()
        )
        if not item:
            item = ItemOrcamento(
                id_orcamento=orc.id,
                id_produto=produto.id,
                quantidade=quantidade,
                valor_unitario=preco,
                subtotal=subtotal_add,
            )
            db.add(item)
        else:
            nova_qtd = float(item.quantidade) + float(quantidade)
            item.quantidade = nova_qtd
            item.valor_unitario = preco
            item.subtotal = round(nova_qtd * preco, 2)

        recompute_orcamento_total(db, orc)
        db.commit()
        return True, "Item adicionado ao orçamento."
    except Exception as e:
        db.rollback()
        return False, f"Erro ao adicionar no orçamento: {e}"
    finally:
        db.close()


def reset_orcamento(session_id: str) -> str:
    db: Session = SessionLocal()
    try:
        orc = (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
        if not orc:
            return "Seu orçamento já está vazio."
        db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).delete()
        orc.total_aproximado = 0
        db.commit()
        return "Zerei seu orçamento atual."
    except Exception as e:
        db.rollback()
        return f"Tive um problema ao limpar o orçamento: {e}"
    finally:
        db.close()


def format_orcamento(session_id: str) -> str:
    db: Session = SessionLocal()
    try:
        orc = (
            db.query(Orcamento)
            .filter(Orcamento.user_id == session_id, Orcamento.status == "aberto")
            .first()
        )
        if not orc:
            return "Seu orçamento está vazio."

        itens = db.query(ItemOrcamento).filter(ItemOrcamento.id_orcamento == orc.id).all()
        if not itens:
            return "Seu orçamento está vazio."

        linhas = ["Resumo do orçamento:"]
        total = 0.0
        for it in itens:
            prod = it.produto
            if not prod:
                continue
            qtd = float(it.quantidade)
            vu = float(it.valor_unitario)
            sub = float(it.subtotal)
            total += sub
            linhas.append(f"- {qtd:.0f} x {prod.nome} (R$ {vu:.2f} cada) = R$ {sub:.2f}")

        linhas.append(f"\nTotal aproximado: R$ {total:.2f}")
        return "\n".join(linhas)
    finally:
        db.close()


# ============================
# Tools (internas)
# ============================

@tool
def informa_horario_funcionamento() -> str:
    """Informa o horário de funcionamento da loja."""
    return HORARIO_LOJA


@tool
def verifica_entrega_bairro(bairro: str) -> str:
    """Verifica se a loja faz entrega no bairro informado."""
    b = strip_accents((bairro or "").strip().lower())
    allowed = [strip_accents(x) for x in BAIRROS_ENTREGA]
    if b in allowed:
        return f"Sim, fazemos entrega no bairro {bairro.title()}."
    return f"No momento, não fazemos entrega no bairro {bairro.title()}."


@tool
def registrar_endereco(session_id: str, endereco_texto: str) -> str:
    """Registra endereço/CEP/bairro no estado da sessão."""
    st = get_state(session_id)
    st["endereco"] = (endereco_texto or "").strip()

    m = CEP_REGEX.search(endereco_texto or "")
    if m:
        st["cep"] = m.group(0)

    low = strip_accents((endereco_texto or "").lower())
    for b in BAIRROS_ENTREGA:
        if strip_accents(b) in low:
            st["bairro"] = b
            break
    return "Endereço registrado."


@tool
def set_preferencia_pagamento_entrega(
    session_id: str,
    entrega_ou_retirada: Optional[str] = None,
    forma_pagamento: Optional[str] = None,
) -> str:
    """Salva preferência de entrega/retirada e forma de pagamento no estado da sessão."""
    st = get_state(session_id)
    if entrega_ou_retirada:
        v = _norm(entrega_ou_retirada)
        if "entrega" in v:
            st["preferencia_entrega"] = "entrega"
        elif "retirada" in v or "retirar" in v:
            st["preferencia_entrega"] = "retirada"

    if forma_pagamento:
        v = _norm(forma_pagamento)
        if "pix" in v:
            st["forma_pagamento"] = "pix"
        elif "dinheiro" in v:
            st["forma_pagamento"] = "dinheiro"
        elif "cartao" in v or "credito" in v or "debito" in v:
            st["forma_pagamento"] = "cartão"

    return "Preferências registradas."


# ============================
# Persistência do chat
# ============================

def save_chat_db(session_id: str, message: str, reply: str, needs_human: bool) -> None:
    db: Session = SessionLocal()
    try:
        registro = ChatHistory(
            user_id=session_id,
            message=message,
            reply=reply,
            needs_human=needs_human,
        )
        db.add(registro)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ============================
# Parsing quantidade e hint
# ============================

def extract_kg_quantity(message: str) -> Optional[float]:
    t = _norm(message)
    m = re.search(r"(\d+[,.]?\d*)\s*kg\b", t)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def extract_units_quantity(message: str) -> Optional[float]:
    t = _norm(message)
    m = re.search(r"(\d+[,.]?\d*)\s*(saco|sacos|un|unidade|unidades)\b", t)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def extract_plain_number(message: str) -> Optional[float]:
    t = _norm(message)
    if re.fullmatch(r"\d+[,.]?\d*", t):
        return float(t.replace(",", "."))
    return None


def packaging_kg_in_name(prod_name: str) -> Optional[int]:
    n = _norm(prod_name)
    m = re.search(r"\b(20|25|50)\s*kg\b", n)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b(20|25|50)kg\b", n)
    if m2:
        return int(m2.group(1))
    return None


def suggest_units_from_packaging(prod_name: str, kg_qty: float) -> Optional[Tuple[float, str]]:
    pkg = packaging_kg_in_name(prod_name)
    if not pkg:
        return None
    units = kg_qty / float(pkg)
    units_rounded = round(units)
    if abs(units - units_rounded) < 1e-6:
        units = float(units_rounded)
    return units, f"{kg_qty:.0f}kg ≈ {units:.0f} saco(s) de {pkg}kg"


def extract_product_hint(message: str) -> Optional[str]:
    """
    - Não quebra "trena de 5m"
    - Continua funcionando para "200kg de cimento"
    - Evita misturar duas coisas ("cimento e trena") -> pega só o primeiro item antes do " e "
    """
    txt = _norm(message)
    if CEP_REGEX.search(message or ""):
        return None

    m = re.search(r"\b(quero|queria|preciso|gostaria|comprar|pedido)\b\s+(.*)$", txt)
    rest = m.group(2) if m else txt

    # se tiver " e " pega só o primeiro pedido (evita "cimento trena 5m" junto)
    if " e " in rest:
        rest = rest.split(" e ")[0].strip()

    # Só corta o que vem depois de "de" se for caso do tipo: "200kg de cimento"
    # (quantidade + unidade + de + produto)
    if re.search(r"\b(\d+[,.]?\d*)\s*(kg|quilo|quilos|saco|sacos|un|unidade|unidades)\s+de\s+", rest):
        rest = re.split(r"\bde\b", rest, maxsplit=1)[1].strip()

    # remove "para entrega", etc.
    rest = re.split(r"\b(para|entrega|retirada)\b", rest)[0].strip()

    tokens = []
    for tok in rest.split():
        if tok in STOPWORDS:
            continue
        if tok in UNITS_WORDS:
            continue
        if re.fullmatch(r"\d+[,.]?\d*", tok):
            continue
        tokens.append(tok)

    if not tokens:
        return None
    return " ".join(tokens[:6]).strip() or None


# ============================
# Busca de produtos (fuzzy)
# ============================

def db_find_best_products(query: str, k: int = 5) -> List[Produto]:
    db: Session = SessionLocal()
    try:
        produtos = db.query(Produto).filter(Produto.ativo == True).all()
        if not produtos:
            return []

        qn = _norm(query)
        q_words = [w for w in qn.split() if w and w not in STOPWORDS]

        scored: List[Tuple[float, Produto]] = []
        for p in produtos:
            textp = _norm(f"{p.nome} {p.descricao or ''}")

            token_score = 0.0
            for w in q_words:
                if re.search(rf"\b{re.escape(w)}\b", textp):
                    token_score += 1.0

            seq_score = SequenceMatcher(None, qn, _norm(p.nome)).ratio()
            score = token_score * 2.0 + seq_score

            if score > 0.4:
                scored.append((score, p))

        # dedup por nome
        best_by_name: Dict[str, Tuple[float, Produto]] = {}
        for score, p in scored:
            key = (_norm(p.nome) or "").strip()
            if key and (key not in best_by_name or score > best_by_name[key][0]):
                best_by_name[key] = (score, p)

        ranked = sorted(best_by_name.values(), key=lambda x: x[0], reverse=True)
        return [p for _, p in ranked[:k]]
    finally:
        db.close()


def store_suggestions(session_id: str, produtos: List[Produto], hint: str, requested_kg: Optional[float]) -> None:
    st = get_state(session_id)
    st["last_suggestions"] = [{"id": p.id, "nome": p.nome} for p in produtos]
    st["last_hint"] = hint
    st["last_requested_kg"] = requested_kg


def format_options(produtos: List[Produto]) -> str:
    lines = []
    for i, p in enumerate(produtos, start=1):
        preco = float(p.preco) if p.preco is not None else 0.0
        estoque = float(p.estoque_atual) if p.estoque_atual is not None else 0.0
        un = p.unidade or "UN"
        lines.append(f"{i}) {p.nome} — R$ {preco:.2f}/{un} — estoque {estoque:.0f}")
    return "\n".join(lines)


def parse_choice_indices(message: str, max_len: int) -> List[int]:
    """
    Aceita: "1", "1 e 3", "1,3", "1 3"
    Retorna índices 0-based únicos, na ordem.
    """
    t = _norm(message)
    nums = [int(x) for x in re.findall(r"\b\d+\b", t)]
    out: List[int] = []
    seen = set()
    for n in nums:
        idx = n - 1
        if 0 <= idx < max_len and idx not in seen:
            out.append(idx)
            seen.add(idx)
    return out


def resolve_selected_products(session_id: str, message: str) -> List[Produto]:
    """
    Tenta resolver 1 ou múltiplas escolhas a partir das sugestões.
    """
    st = get_state(session_id)
    suggestions = st.get("last_suggestions") or []
    if not suggestions:
        return []

    indices = parse_choice_indices(message, max_len=len(suggestions))
    if not indices:
        return []

    ids = [suggestions[i]["id"] for i in indices]
    db: Session = SessionLocal()
    try:
        products = (
            db.query(Produto)
            .filter(Produto.id.in_(ids), Produto.ativo == True)
            .all()
        )
        by_id = {p.id: p for p in products}
        ordered = [by_id[i] for i in ids if i in by_id]
        return ordered
    finally:
        db.close()


# ============================
# Fluxo pendente (quantidade)
# ============================

def set_pending_for_qty(session_id: str, produto: Produto, requested_kg: Optional[float]) -> str:
    st = get_state(session_id)
    st["pending_product_id"] = produto.id
    st["awaiting_qty"] = True

    suggested_units = None
    ask = "\n\nQuantas unidades/sacos você quer? (ex.: 1, 4 sacos ou 200kg)"

    if requested_kg is not None:
        conv = suggest_units_from_packaging(produto.nome, requested_kg)
        if conv:
            suggested_units, conv_text = conv
            st["pending_suggested_units"] = suggested_units
            ask = (
                "\n\nPelo que você pediu: "
                f"**{conv_text}**.\n"
                f"Quer que eu adicione **{int(suggested_units)}** no orçamento? "
                "(responda **sim** ou diga outra quantidade)"
            )
        else:
            st["pending_suggested_units"] = None
    else:
        st["pending_suggested_units"] = None

    preco = float(produto.preco) if produto.preco is not None else 0.0
    estoque = float(produto.estoque_atual) if produto.estoque_atual is not None else 0.0
    un = produto.unidade or "UN"

    return (
        f"Beleza — **{produto.nome}**.\n"
        f"Preço: R$ {preco:.2f}/{un} | Estoque: {estoque:.0f} {un}."
        + ask
    )


def handle_pending_qty(session_id: str, message: str) -> Optional[str]:
    st = get_state(session_id)
    if not st.get("awaiting_qty") or not st.get("pending_product_id"):
        return None

    db: Session = SessionLocal()
    try:
        produto = db.query(Produto).filter(Produto.id == st["pending_product_id"], Produto.ativo == True).first()
    finally:
        db.close()

    if not produto:
        st["awaiting_qty"] = False
        st["pending_product_id"] = None
        st["pending_suggested_units"] = None
        return "Certo — não consegui localizar esse produto agora. Me diga novamente qual produto você quer."

    # determina qty
    if is_affirmative(message) and st.get("pending_suggested_units") is not None:
        qty_un = float(st["pending_suggested_units"])
    else:
        kg_qty = extract_kg_quantity(message)
        unit_qty = extract_units_quantity(message)
        plain = extract_plain_number(message)

        qty_un = None

        if kg_qty is not None:
            conv = suggest_units_from_packaging(produto.nome, kg_qty)
            if conv:
                qty_un, _ = conv
            else:
                return "Entendi os kg, mas este item não indica o peso por saco/unidade. Me diga quantas unidades você quer (ex.: 4)."

        if unit_qty is not None:
            qty_un = unit_qty

        if qty_un is None and plain is not None:
            qty_un = plain

        if qty_un is None:
            suggested = st.get("pending_suggested_units")
            if suggested is not None:
                return f"Quer que eu adicione **{int(suggested)}** unidades no orçamento? (responda **sim** ou diga outra quantidade)"
            return "Quantas unidades/sacos você quer? (ex.: 1, 4 sacos ou 200kg)"

    if qty_un <= 0:
        return "A quantidade precisa ser maior que zero. Quantas unidades/sacos você quer?"

    preco = float(produto.preco) if produto.preco is not None else 0.0
    estoque = float(produto.estoque_atual) if produto.estoque_atual is not None else 0.0
    un = produto.unidade or "UN"

    if estoque <= 0:
        st["awaiting_qty"] = False
        st["pending_product_id"] = None
        st["pending_suggested_units"] = None
        return f"Encontrei **{produto.nome}**, mas está **sem estoque** no momento. Quer escolher outra opção?"

    if qty_un > estoque:
        qty_un = estoque

    # idempotência simples
    usern = _norm(message)
    signature = f"{produto.id}:{int(qty_un)}"
    if st.get("last_added_signature") == signature and st.get("last_user_norm") == usern:
        return f"Ok — já estava no seu orçamento.\n\n{format_orcamento(session_id)}"

    ok, msg_add = add_item_to_orcamento(session_id, produto, float(qty_un))
    st["last_added_signature"] = signature
    st["last_user_norm"] = usern

    # limpa pendência atual
    st["awaiting_qty"] = False
    st["pending_product_id"] = None
    st["pending_suggested_units"] = None

    subtotal = float(qty_un) * preco
    resumo = format_orcamento(session_id)

    # se tem fila (ex.: "1 e 3"), já chama próximo item
    if st.get("selection_queue"):
        next_id = st["selection_queue"].pop(0)
        db2: Session = SessionLocal()
        try:
            next_prod = db2.query(Produto).filter(Produto.id == next_id, Produto.ativo == True).first()
        finally:
            db2.close()

        base = (
            f"✅ {msg_add}\n"
            f"Item: **{produto.nome}**\n"
            f"Quantidade: **{qty_un:.0f} {un}**\n"
            f"Subtotal aprox.: **R$ {subtotal:.2f}**\n\n"
            f"{resumo}\n\n"
        )
        if next_prod:
            base += "Agora o próximo item:\n\n" + set_pending_for_qty(session_id, next_prod, requested_kg=None)
        else:
            base += "Não consegui carregar o próximo item da fila. Pode me dizer qual produto falta?"
        return base

    # perguntas finais (máx 2)
    questions = []
    if not st.get("preferencia_entrega"):
        questions.append("Vai ser **entrega** ou **retirada**?")
    if st.get("preferencia_entrega") == "entrega" and not st.get("bairro"):
        questions.append("Qual **bairro** da entrega? (ou mande o **endereço/CEP**)")

    if len(questions) < 2 and not st.get("forma_pagamento"):
        questions.append("Vai pagar no **PIX**, **cartão** ou **dinheiro**?")

    reply = (
        f"✅ {msg_add}\n"
        f"Item: **{produto.nome}**\n"
        f"Quantidade: **{qty_un:.0f} {un}**\n"
        f"Subtotal aprox.: **R$ {subtotal:.2f}**\n\n"
        f"{resumo}"
    )
    if questions:
        reply += "\n\n" + " ".join(questions)
    return reply


# ============================
# Preferências / endereço
# ============================

def handle_preferences(message: str, session_id: str) -> bool:
    """
    Retorna True se atualizou alguma preferência.
    """
    t = _norm(message)
    entrega_ou_retirada = None
    forma_pagamento = None

    if "entrega" in t:
        entrega_ou_retirada = "entrega"
    if "retirada" in t or "retirar" in t:
        entrega_ou_retirada = "retirada"

    if "pix" in t:
        forma_pagamento = "pix"
    elif "dinheiro" in t:
        forma_pagamento = "dinheiro"
    elif "cartao" in t or "credito" in t or "debito" in t:
        forma_pagamento = "cartão"

    if entrega_ou_retirada or forma_pagamento:
        set_preferencia_pagamento_entrega.invoke({
            "session_id": session_id,
            "entrega_ou_retirada": entrega_ou_retirada,
            "forma_pagamento": forma_pagamento,
        })
        return True
    return False


def maybe_register_address(message: str, session_id: str) -> bool:
    if CEP_REGEX.search(message or ""):
        registrar_endereco.invoke({"session_id": session_id, "endereco_texto": message})
        return True
    return False


def reply_after_preference(session_id: str) -> str:
    st = get_state(session_id)
    resumo = format_orcamento(session_id)

    parts = []
    if st.get("preferencia_entrega"):
        parts.append(f"Beleza — anotei **{st['preferencia_entrega']}**.")
    if st.get("forma_pagamento"):
        parts.append(f"Pagamento: **{st['forma_pagamento']}**.")
    if st.get("bairro"):
        parts.append(f"Bairro: **{st['bairro']}**.")
    if st.get("cep"):
        parts.append(f"CEP: **{st['cep']}**.")

    reply = ""
    if parts:
        reply += " ".join(parts) + "\n\n"
    reply += resumo

    # próximos passos
    questions = []
    if st.get("preferencia_entrega") == "entrega" and not (st.get("bairro") or st.get("endereco")):
        questions.append("Me diga o **bairro** ou mande o **endereço/CEP** para entrega.")
    if not st.get("forma_pagamento"):
        questions.append("Vai pagar no **PIX**, **cartão** ou **dinheiro**?")

    if questions:
        reply += "\n\n" + " ".join(questions)

    return reply


# ============================
# Auto-sugestão de produtos
# ============================

def auto_suggest_products(message: str, session_id: str) -> Optional[str]:
    # Não sugere catálogo para "bom dia" / preferências
    if is_greeting(message) or message_is_preferences_only(message):
        return None
    if not has_product_intent(message):
        return None

    hint = extract_product_hint(message)
    if not hint or len(hint) < 2:
        return None

    produtos = db_find_best_products(hint, k=5)
    if not produtos:
        return None

    requested_kg = extract_kg_quantity(message)
    store_suggestions(session_id, produtos, hint, requested_kg)

    extra = ""
    if requested_kg is not None and produtos:
        conv = suggest_units_from_packaging(produtos[0].nome, requested_kg)
        if conv:
            _, conv_text = conv
            extra = f"\n\nPelo que você pediu: **{conv_text}**."

    return (
        f"Encontrei estas opções no catálogo para **{hint}**:\n\n"
        f"{format_options(produtos)}\n\n"
        "Qual você quer? (responda **1**, **2**, **3**… ou escreva o nome parecido)"
        + extra
    )


# ============================
# Endpoint
# ============================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    message = body.message or ""
    session_id = (body.user_id or "").strip() or uuid4().hex
    st = get_state(session_id)

    try:
        # 0) cumprimentos
        if is_greeting(message):
            reply = "Bom dia! 🙂 Como posso ajudar? (ex.: cimento, areia, trena, etc.)"
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 1) horário
        if is_hours_question(message):
            reply = informa_horario_funcionamento.invoke({})
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 2) entrega por bairro
        b = detect_delivery_bairro(message)
        if b:
            reply = verifica_entrega_bairro.invoke({"bairro": b})
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 3) ver orçamento
        if is_cart_show_request(message):
            reply = format_orcamento(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 4) limpar orçamento
        if is_cart_reset_request(message):
            reply = reset_orcamento(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 5) registrar endereço se tiver CEP
        if maybe_register_address(message, session_id):
            reply = "Perfeito, registrei o endereço. Agora me diga se vai ser **entrega** ou **retirada** e a forma de pagamento (PIX/cartão/dinheiro)."
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 6) preferências (entrega/pix/etc)
        changed_pref = handle_preferences(message, session_id)

        # 7) se for só preferência, responde com resumo + próximo passo (não cai no fallback)
        if changed_pref and message_is_preferences_only(message) and not st.get("awaiting_qty") and not st.get("last_suggestions"):
            reply = reply_after_preference(session_id)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 8) se aguardando quantidade, resolve
        pending_reply = handle_pending_qty(session_id, message)
        if pending_reply:
            pending_reply = sanitize_reply(pending_reply)
            save_chat_db(session_id, message, pending_reply, False)
            return ChatResponse(reply=pending_reply, needs_human=False, session_id=session_id)

        # 9) se tem sugestões e o usuário escolheu (1 / 1 e 3)
        selected_products = resolve_selected_products(session_id, message)
        if selected_products:
            # limpa sugestões
            requested_kg = st.get("last_requested_kg")
            st["last_suggestions"] = []
            st["last_hint"] = None

            # se escolheu mais de um, fila
            if len(selected_products) > 1:
                st["selection_queue"] = [p.id for p in selected_products[1:]]
            else:
                st["selection_queue"] = []

            first = selected_products[0]
            reply = set_pending_for_qty(session_id, first, requested_kg=requested_kg)
            reply = sanitize_reply(reply)
            save_chat_db(session_id, message, reply, False)
            return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

        # 10) auto sugestão
        suggested = auto_suggest_products(message, session_id=session_id)
        if suggested:
            suggested = sanitize_reply(suggested)
            save_chat_db(session_id, message, suggested, False)
            return ChatResponse(reply=suggested, needs_human=False, session_id=session_id)

        # 11) fallback amigável (mas agora não ignora que já existe orçamento)
        resumo = format_orcamento(session_id)
        if "Seu orçamento está vazio" not in resumo:
            reply = (
                f"{resumo}\n\n"
                "Se quiser adicionar mais itens, diga algo como: “quero uma trena 5m” ou “quero 100kg de cimento”.\n"
                "Se quiser finalizar, diga **entrega** ou **retirada** e a forma de pagamento."
            )
        else:
            reply = (
                "Certo! Me diga o que você precisa.\n"
                "- Ex.: “quero 200kg de cimento”, “quero 4 sacos de cimento CP II”, “uma trena 5m”.\n"
                "Se você disser só o item (ex.: “cimento”), eu te mostro as opções do catálogo."
            )

        reply = sanitize_reply(reply)
        save_chat_db(session_id, message, reply, False)
        return ChatResponse(reply=reply, needs_human=False, session_id=session_id)

    except Exception:
        traceback.print_exc()
        reply = "Tive um problema ao processar sua mensagem agora. Você pode tentar novamente."
        reply = sanitize_reply(reply)
        save_chat_db(session_id, message, reply, True)
        return ChatResponse(reply=reply, needs_human=True, session_id=session_id)
