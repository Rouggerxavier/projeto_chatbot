"""
Conversation Engine com slots e politica de perguntas para evitar loops.

Foco inicial: categoria tubos/conexoes (PVC etc).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional, List, Tuple

from app.text_utils import norm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slot schema e normalizacao
# ---------------------------------------------------------------------------

PIPE_ITEMS = {
    "joelho": {"aliases": ["cotovelo", "joelho", "joelho pvc", "joelho de pvc"]},
    "tubo": {"aliases": ["cano", "tubo", "tubulacao"]},
    "luva": {"aliases": ["luva", "encaixe"]},
    "t": {"aliases": ["t", "te", "tee"]},
    "reducao": {"aliases": ["reducao", "adaptador", "bucha"]},
}

PIPE_MATERIALS = {
    "pvc": ["pvc"],
    "cpvc": ["cpvc"],
    "ppr": ["ppr"],
    "cobre": ["cobre"],
    "galvanizado": ["galvanizado", "aco galvanizado"],
}

SYSTEM_USE = {
    "agua_fria": ["agua fria", "água fria", "fria"],
    "agua_quente": ["agua quente", "água quente", "quente"],
    "esgoto": ["esgoto", "esgotamento", "esgotar"],
    "pluvial": ["pluvial", "chuva", "drenagem"],
    "gas": ["gas", "gás"],
    "irrigacao": ["irrigacao", "irrigação"],
}

CONNECTION_TYPE = {
    "soldavel": ["soldavel", "soldável", "colar"],
    "roscavel": ["roscavel", "roscável", "rosca"],
    "bolsa": ["bolsa", "ponta e bolsa", "ponta/boca"],
    "ponta_ponta": ["ponta", "ponta a ponta", "ponta/ponta"],
}

ANGLES = {"45": ["45", "45°", "45 graus"], "90": ["90", "90°", "90 graus"]}

BITOLA_REGEX = re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?)(mm|mm?m|pol|\"|')?\b", re.IGNORECASE)


def _lookup(value: str, table: Dict[str, List[str]]) -> Optional[str]:
    if not value:
        return None
    t = norm(value)
    for key, aliases in table.items():
        if key == t or t in aliases:
            return key
        for alias in aliases:
            if alias in t:
                return key
    return None


def _extract_bitola(text: str) -> Optional[str]:
    for match in BITOLA_REGEX.finditer(text):
        num, unit = match.groups()
        if not num:
            continue
        num = num.replace(",", ".")
        unit = (unit or "").lower()
        if unit in {"", "mm", "mmm"}:
            return f"{num}mm"
        if "pol" in unit or '"' in unit or "'" in unit:
            return f'{num}"'
        return num
    return None


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract_slots(message: str, current_slots: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai/normaliza slots de tubos/conexoes a partir da mensagem.
    Rule-based + pronto para acoplar LLM (placeholder).
    """
    slots = dict(current_slots or {})
    t = norm(message or "")

    # item
    def _has_word(word: str) -> bool:
        return bool(re.search(rf"\b{re.escape(word)}\b", t))

    for key, cfg in PIPE_ITEMS.items():
        if _has_word(key):
            slots.setdefault("item", key)
            break
        for alias in cfg["aliases"]:
            if _has_word(alias):
                slots.setdefault("item", key)
                break
        if slots.get("item"):
            break

    # material
    mat = _lookup(t, PIPE_MATERIALS)
    if mat:
        slots.setdefault("material", mat)

    # angulo (para joelho)
    ang = _lookup(t, ANGLES)
    if ang:
        slots.setdefault("angulo", ang)

    # sistema_uso
    sys_use = _lookup(t, SYSTEM_USE)
    if sys_use:
        slots.setdefault("sistema_uso", sys_use)

    # tipo_conexao
    conn = _lookup(t, CONNECTION_TYPE)
    if conn:
        slots.setdefault("tipo_conexao", conn)

    # diametro/bitola
    bit = _extract_bitola(message)
    if bit:
        slots.setdefault("diametro", bit)

    # contexto_instalacao (parede/piso/etc) apenas para registrar
    for ctx in ["parede", "piso", "teto", "laje", "banheiro", "cozinha"]:
        if ctx in t:
            slots.setdefault("contexto_instalacao", ctx)
            break

    # “apenas X” significa restricao, nao pergunta novamente
    if "apenas" in t and "joelho" in t:
        slots.setdefault("restricao_item", "apenas_item")

    return slots


# ---------------------------------------------------------------------------
# Ask policy
# ---------------------------------------------------------------------------

def _asked_recently(slot: str, last_questions: List[str]) -> bool:
    if not slot:
        return False
    tail = (last_questions or [])[-3:]
    return slot in tail


def _asked_count(slot: str, last_questions: List[str]) -> int:
    return (last_questions or []).count(slot)


def next_step(
    intent: str,
    slots: Dict[str, Any],
    last_questions: List[str],
) -> Dict[str, Any]:
    """
    Decide a próxima pergunta ou ação com base nos slots coletados.
    Retorna dict {"action": "ask|confirm|ask_qty", "slot": ..., "question": ...}
    """
    slots = slots or {}
    last_questions = last_questions or []

    def ask(slot: str, text: str) -> Dict[str, Any]:
        return {"action": "ask", "slot": slot, "question": text}

    # Se item/material/sistema_uso presentes e diametro presente -> confirmar e pedir quantidade
    required = ["item", "material", "sistema_uso"]
    if all(slots.get(r) for r in required) and slots.get("diametro"):
        summary = _summarize(slots)
        return {
            "action": "ask_qty",
            "slot": "quantidade",
            "question": f"Certo: {summary}. Quantas unidades voce precisa?",
        }

    # Se item/material/sistema_uso presentes mas sem diametro -> perguntar bitola
    if all(slots.get(r) for r in required) and not slots.get("diametro"):
        if _asked_count("diametro", last_questions) < 2:
            return ask("diametro", "Qual a bitola? (20/25/32/40/50/75mm)")

    # Se item joelho e faltando angulo
    if slots.get("item") == "joelho" and not slots.get("angulo"):
        if _asked_count("angulo", last_questions) < 2:
            return ask("angulo", "Joelho de 45° ou 90°?")

    # Se faltando sistema_uso
    if not slots.get("sistema_uso"):
        if _asked_count("sistema_uso", last_questions) < 2:
            return ask("sistema_uso", "Vai ser para: 1) agua fria 2) agua quente 3) esgoto 4) pluvial?")

    # Se faltando material
    if not slots.get("material"):
        if _asked_count("material", last_questions) < 2:
            return ask("material", "O material e: 1) PVC 2) CPVC 3) PPR 4) outro?")

    # Se faltando item
    if not slots.get("item"):
        if _asked_count("item", last_questions) < 2:
            return ask("item", "Qual peca voce precisa? (joelho, tubo, luva, te, reducao)")

    # Default: confirmar o que tem
    summary = _summarize(slots)
    return {"action": "confirm", "slot": None, "question": f"Entendi: {summary}. Qual bitola voce precisa?"}


def _summarize(slots: Dict[str, Any]) -> str:
    parts = []
    if slots.get("item"):
        parts.append(slots["item"])
    if slots.get("material"):
        parts.append(slots["material"])
    if slots.get("angulo"):
        parts.append(f"{slots['angulo']}°")
    if slots.get("sistema_uso"):
        parts.append(slots["sistema_uso"])
    if slots.get("diametro"):
        parts.append(slots["diametro"])
    return " ".join(parts) or "o item"
