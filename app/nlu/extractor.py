"""
Extractor genérico orientado a LLM (fallback rule-based) para intenção/atributos.
"""
from __future__ import annotations

import re
from typing import Dict, Any, Optional

from app.text_utils import norm
from app import catalog_schema


def _intent_from_text(text: str) -> str:
    t = norm(text)
    buy_markers = ["quero", "preciso", "comprar", "tem", "vende", "vocês tem", "vocês têm"]
    if any(m in t for m in buy_markers):
        return "buy"
    return "unknown"


def _parse_number_with_unit(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\s*(mm|cm|m|pol|\"|l|ml)\b", text, re.IGNORECASE)
    if not m:
        return None
    num, unit = m.groups()
    num = num.replace(",", ".")
    unit = unit.lower()
    return f"{num}{unit}"


def _extract_attributes(category_id: Optional[str], message: str) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    if not category_id:
        return attrs

    schema = catalog_schema.get_category_schema(category_id)
    t = norm(message)

    for attr in schema.get("attributes", []):
        key = attr.get("key")
        options = attr.get("options") or []
        if attr.get("type") == "enum" and options:
            for opt in options:
                if opt in t:
                    attrs[key] = opt
                    break
        elif attr.get("type") == "number":
            val = _parse_number_with_unit(message)
            if val:
                attrs[key] = val
        elif attr.get("type") == "string":
            # captura cor ou texto livre curto
            if len(t.split()) <= 4:
                attrs[key] = t

    # Heuristicas especificas leves (sem hardcode de item)
    if category_id == "tubos_conexoes":
        if "sold" in t:
            attrs.setdefault("tipo_conexao", "soldavel")
        if "rosc" in t:
            attrs.setdefault("tipo_conexao", "roscavel")
        if "esgoto" in t:
            attrs.setdefault("sistema_uso", "esgoto")
        if "agua quente" in t or "água quente" in t:
            attrs.setdefault("sistema_uso", "agua_quente")
        if "agua fria" in t or "água fria" in t:
            attrs.setdefault("sistema_uso", "agua_fria")

    return attrs


def extract(user_message: str, conversation_context: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai JSON estruturado da mensagem (intent, categoria, atributos).
    Fallback rule-based para funcionar offline; projetado para ser substituído por LLM.
    """
    intent = _intent_from_text(user_message)

    # guess category por termos
    category_guess = catalog_schema.find_category(user_message) or conversation_context.get("category_id")

    attributes = _extract_attributes(category_guess, user_message)
    attributes = {**(conversation_context.get("attributes") or {}), **attributes}

    constraints = {}
    t = norm(user_message)
    if "apenas" in t or "so" in t or "só" in t:
        constraints["only_item"] = True

    not_found_signal = {
        "likely_not_in_catalog": False,
        "confidence": 0.0,
        "reason": None,
    }

    if not category_guess:
        not_found_signal = {
            "likely_not_in_catalog": True,
            "confidence": 0.6,
            "reason": "categoria_desconhecida",
        }

    return {
        "intent": intent,
        "product_query": user_message,
        "category_guess": category_guess,
        "attributes": attributes,
        "constraints": constraints,
        "ambiguity_flags": [],
        "not_found_signal": not_found_signal,
    }
