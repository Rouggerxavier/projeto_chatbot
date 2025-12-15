import re
from typing import Tuple

# Coisas que o bot NÃO pode afirmar (porque viram alucinação fácil)
# Ex.: "vou te enviar um e-mail", "código de rastreamento", "QR code PIX", etc.
FORBIDDEN_CLAIMS = re.compile(
    r"(?i)("
    r"\be-?mail\b|"
    r"\brastreamento\b|\brastreio\b|"
    r"\bc[oó]digo\s+de\s+rastre(ia|io)\b|"
    r"\btracking\b|"
    r"\bqr\s*code\b|"
    r"\bc[oó]digo\s+pix\b|"
    r"\bc[oó]digo\s+de\s+barras\b|"
    r"\bser[aá]\s+debitad[oa]\b|"
    r"\b(enviado|enviada|postado|postada|entregue|entregue|a\s+caminho|saiu\s+para\s+entrega)\b"
    r")"
)

# Linhas que frequentemente aparecem como "invenção"
FORBIDDEN_LINES = re.compile(
    r"(?i)("
    r"voc[eê]\s+receber[aá]\s+um?\s+e-?mail|"
    r"c[oó]digo\s+de\s+rastre|"
    r"c[oó]digo\s+pix|"
    r"qr\s*code|"
    r"c[oó]digo\s+de\s+barras|"
    r"pedido\s+foi\s+enviado|"
    r"pedido\s+foi\s+entregue"
    r")"
)

SAFE_NOTE = (
    "Obs.: eu **não envio e-mail**, **não gero rastreio** e **não crio QR/código PIX** aqui no chat. "
    "Eu apenas monto o orçamento/pedido e encaminho para um atendente finalizar."
)

def apply_guardrails(text: str) -> Tuple[str, bool]:
    """
    Remove trechos/linhas com afirmações proibidas e adiciona nota segura.
    Retorna: (texto_limpo, alterou?)
    """
    if not text:
        return text, False

    original = text

    # Se aparecer algo proibido, removemos linhas inteiras que contêm esse conteúdo
    if FORBIDDEN_CLAIMS.search(text) or FORBIDDEN_LINES.search(text):
        kept = []
        for ln in text.splitlines():
            if FORBIDDEN_LINES.search(ln) or FORBIDDEN_CLAIMS.search(ln):
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
