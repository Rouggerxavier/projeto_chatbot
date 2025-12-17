import re
from typing import Tuple

# Nota segura (usada no text_utils)
SAFE_NOTE = (
    "Obs.: eu **não envio e-mail** nem **gera rastreio** aqui no chat. "
    "Eu apenas monto o orçamento/pedido e encaminho para um atendente finalizar."
)

# Coisas que o bot NÃO pode afirmar (porque viram alucinação fácil)
_FORBIDDEN_ANY_PATTERNS = [
    r"\be-?mail\b",
    r"\brastreamento\b",
    r"\brastreio\b",
    r"\bc[oó]digo\s+de\s+rastre(ia|io)\b",
    r"\btracking\b",
    r"\bc[oó]digo\s+de\s+barras\b",
    r"\bser[aá]\s+debitad[oa]\b",
    r"\b(enviado|enviada|postado|postada|entregue|a\s+caminho|saiu\s+para\s+entrega)\b",
]

# Linhas que frequentemente aparecem como "invenção"
_FORBIDDEN_LINE_PATTERNS = [
    r"voc[eê]\s+receber[aá]\s+um?\s+e-?mail",
    r"enviaremos\s+um?\s+e-?mail",
    r"c[oó]digo\s+de\s+rastre",
    r"c[oó]digo\s+de\s+barras",
    r"pedido\s+foi\s+enviado",
    r"pedido\s+foi\s+entregue",
]

FORBIDDEN_ANY = re.compile("|".join(_FORBIDDEN_ANY_PATTERNS), flags=re.IGNORECASE)
FORBIDDEN_LINES = re.compile("|".join(_FORBIDDEN_LINE_PATTERNS), flags=re.IGNORECASE)


def apply_guardrails(text: str) -> Tuple[str, bool]:
    """
    Remove trechos/linhas com afirmações proibidas e adiciona nota segura.
    Retorna: (texto_limpo, alterou?)
    """
    if not text:
        return text, False

    original = text

    # Se aparecer algo proibido, removemos linhas inteiras que contêm esse conteúdo
    if FORBIDDEN_ANY.search(text) or FORBIDDEN_LINES.search(text):
        kept = []
        for ln in text.splitlines():
            if FORBIDDEN_LINES.search(ln) or FORBIDDEN_ANY.search(ln):
                continue
            kept.append(ln)

        text = "\n".join(kept).strip()

        # Se ficou vazio, cai para uma resposta segura genérica
        if not text:
            text = "Certo! Eu consigo montar seu orçamento/pedido por aqui e encaminhar para um atendente finalizar."

        # Garante a nota (uma vez só)
        if SAFE_NOTE.lower() not in text.lower():
            text = text.rstrip() + "\n\n" + SAFE_NOTE

    return text, (text != original)
