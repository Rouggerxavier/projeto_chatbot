"""
Politica generica de conversa baseada em metadados do catalogo.
Pergunta o minimo necessario e escolhe atributo que mais reduz candidatos.
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from app import catalog_schema
from app.text_utils import norm


def _options_text(attr: Dict[str, Any]) -> str:
    opts = attr.get("options") or []
    if not opts:
        return ""
    return " (" + "/".join(opts) + ")"


def _attribute_missing(schema_attrs: List[Dict[str, Any]], attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
    missing = []
    for attr in schema_attrs:
        key = attr.get("key")
        if attr.get("required_for_purchase") and not attributes.get(key):
            missing.append(attr)
    return missing


def _info_gain_attribute(missing: List[Dict[str, Any]], candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates or len(candidates) <= 1:
        return None
    best = None
    best_score = -1
    for attr in missing:
        key = attr.get("key")
        buckets = {}
        for c in candidates:
            val = (c.get("attributes") or {}).get(key)
            buckets.setdefault(val, 0)
            buckets[val] += 1
        if len(buckets) <= 1:
            continue
        # score simples: mais particoes => mais ganho
        score = len(buckets)
        if score > best_score:
            best_score = score
            best = attr
    return best


def next_action(
    category_id: str,
    attributes: Dict[str, Any],
    asked_attributes: Dict[str, int],
    candidates: List[Dict[str, Any]],
    candidate_count_total: Optional[int] = None,
    not_found_signal: Optional[Dict[str, Any]] = None,
    related_items: Optional[List[str]] = None,
) -> Dict[str, Any]:
    schema = catalog_schema.get_category_schema(category_id)
    attrs_meta = schema.get("attributes", [])

    attributes = attributes or {}
    asked_attributes = asked_attributes or {}
    candidates = candidates or []
    candidate_count_total = candidate_count_total if candidate_count_total is not None else len(candidates)

    # NOT FOUND handling
    nf = not_found_signal or {}
    if (candidate_count_total == 0 and not attributes) or nf.get("likely_not_in_catalog"):
        msg = "Não encontrei esse item no nosso catálogo agora."
        follow = "Você quer um equivalente ou uma alternativa parecida?"
        question = f"{msg} {follow}"
        return {
            "action": "not_found",
            "slot": None,
            "question": question,
            "related_items": (related_items or [])[:3],
        }

    missing_required = _attribute_missing(attrs_meta, attributes)

    # stop-asking: se todos required e (candidato único ou nenhum conflito) => pedir quantidade, se ainda não temos quantidade
    if not missing_required:
        if not attributes.get("quantidade"):
            return {
                "action": "ask_qty",
                "slot": "quantidade",
                "question": "Qual quantidade você precisa?",
            }
        # quantidade já presente: nada a perguntar aqui
        return {"action": "confirm", "slot": None, "question": "Certo, vou seguir com seu pedido."}

    # escolher atributo a perguntar: informação + required + não saturado
    attr_choice = _info_gain_attribute(missing_required, candidates) or missing_required[0]

    key = attr_choice.get("key")
    ask_count = asked_attributes.get(key, 0)
    if ask_count >= 2:
        # já perguntou demais, pega proximo se houver
        alt = [a for a in missing_required if a.get("key") != key]
        if alt:
            attr_choice = alt[0]
            key = attr_choice.get("key")

    # pergunta
    question = attr_choice.get("question_template") or f"Preciso do atributo {key}"
    opts_text = _options_text(attr_choice)
    if opts_text:
        question = question.rstrip("?") + opts_text

    return {"action": "ask", "slot": key, "question": question}
