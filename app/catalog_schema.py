"""
Esquema de categorias/atributos para orientar a conversa (dados, não código).

Adicionar nova categoria = apenas editar este arquivo.
"""

from typing import Dict, Any, List, Optional


CATEGORY_SCHEMA: Dict[str, Dict[str, Any]] = {
    "tubos_conexoes": {
        "searchable_terms": [
            "tubo",
            "cano",
            "joelho",
            "luva",
            "te",
            "tee",
            "reducao",
            "pvc",
            "cpvc",
            "ppr",
        ],
        "attributes": [
            {
                "key": "item",
                "type": "enum",
                "required_for_purchase": True,
                "affects_sku": True,
                "options": ["tubo", "joelho", "luva", "te", "reducao"],
                "question_template": "Qual peça voce precisa? (tubo, joelho, luva, te, reducao)",
            },
            {
                "key": "sistema_uso",
                "type": "enum",
                "required_for_purchase": True,
                "affects_sku": True,
                "options": ["agua_fria", "agua_quente", "esgoto", "pluvial", "gas"],
                "question_template": "É para: 1) água fria 2) água quente 3) esgoto 4) pluvial 5) gás?",
            },
            {
                "key": "material",
                "type": "enum",
                "required_for_purchase": True,
                "affects_sku": True,
                "options": ["pvc", "cpvc", "ppr", "cobre", "galvanizado"],
                "question_template": "Material: PVC, CPVC, PPR, cobre ou galvanizado?",
            },
            {
                "key": "angulo",
                "type": "enum",
                "required_for_purchase": False,
                "affects_sku": True,
                "options": ["45", "90"],
                "question_template": "Joelho de 45° ou 90°?",
            },
            {
                "key": "diametro",
                "type": "number",
                "required_for_purchase": True,
                "affects_sku": True,
                "units": ["mm", '\"'],
                "question_template": "Qual a bitola? (20/25/32/40/50/75mm)",
            },
            {
                "key": "tipo_conexao",
                "type": "enum",
                "required_for_purchase": False,
                "affects_sku": True,
                "options": ["soldavel", "roscavel", "bolsa", "ponta_ponta"],
                "question_template": "É soldável, roscável, bolsa ou ponta-ponta?",
            },
        ],
        "related_items": ["cola_pvc", "lixa", "vedarosca", "serra", "trena"],
    },
    "tintas": {
        "searchable_terms": ["tinta", "pintura", "pintar"],
        "attributes": [
            {
                "key": "base",
                "type": "enum",
                "required_for_purchase": True,
                "affects_sku": True,
                "options": ["agua", "solvente"],
                "question_template": "A base é água ou solvente?",
            },
            {
                "key": "ambiente",
                "type": "enum",
                "required_for_purchase": True,
                "affects_sku": True,
                "options": ["interna", "externa"],
                "question_template": "É para ambiente interno ou externo?",
            },
            {
                "key": "acabamento",
                "type": "enum",
                "required_for_purchase": False,
                "affects_sku": True,
                "options": ["fosco", "acetinado", "brilhante"],
                "question_template": "Acabamento: fosco, acetinado ou brilhante?",
            },
            {
                "key": "volume",
                "type": "number",
                "required_for_purchase": False,
                "affects_sku": True,
                "units": ["l", "ml"],
                "question_template": "Qual volume? (ex.: 3,6L, 18L)",
            },
            {
                "key": "cor",
                "type": "string",
                "required_for_purchase": False,
                "affects_sku": False,
                "question_template": "Alguma cor específica?",
            },
        ],
        "related_items": ["rolo", "pincel", "fita_crepe", "lixa", "massa_corrida", "bandeja", "selador"],
    },
}


def find_category(term: str) -> Optional[str]:
    from app.text_utils import norm
    import re

    if not term:
        return None
    t = norm(term)

    def _match_alias(text: str, alias: str) -> bool:
        # se alias tem espaco, usa substring direta
        if " " in alias:
            return alias in text
        # caso contrario, match por palavra inteira
        return bool(re.search(rf"\b{re.escape(alias)}\b", text))

    for cid, cfg in CATEGORY_SCHEMA.items():
        for alias in cfg.get("searchable_terms", []):
            if _match_alias(t, norm(alias)):
                return cid
    return None


def get_category_schema(category_id: str) -> Dict[str, Any]:
    return CATEGORY_SCHEMA.get(category_id, {})


def required_attributes(category_id: str) -> List[str]:
    schema = get_category_schema(category_id)
    attrs = schema.get("attributes", [])
    return [a["key"] for a in attrs if a.get("required_for_purchase")]


def attribute_meta(category_id: str, key: str) -> Optional[Dict[str, Any]]:
    schema = get_category_schema(category_id)
    for attr in schema.get("attributes", []):
        if attr.get("key") == key:
            return attr
    return None
