import re
from typing import Dict, Any, List, Optional

from app.text_utils import norm, BASE_PRODUCT_WORDS


def _normalize_cp(token: str) -> Optional[str]:
    t = norm(token)
    if not t:
        return None
    t = t.replace("cpiii", "cp iii").replace("cp3", "cp iii")
    t = t.replace("cpiv", "cp iv").replace("cp4", "cp iv")
    t = t.replace("cpii", "cp ii").replace("cp2", "cp ii")
    t = t.replace("cpi", "cp i").replace("cp1", "cp i")
    if t.startswith("cp "):
        return t
    return None


def _normalize_ac(token: str) -> Optional[str]:
    t = norm(token)
    if not t:
        return None
    t = t.replace("aciii", "ac iii").replace("ac3", "ac iii")
    t = t.replace("acii", "ac ii").replace("ac2", "ac ii")
    if t.startswith("ac "):
        return t
    return None


def extract_catalog_constraints_from_consultive(
    summary_text: str,
    product_hint: Optional[str],
    known_context: Dict[str, Any],
) -> Dict[str, Any]:
    text = norm(summary_text or "")
    ph = norm(product_hint or "")

    category_hint = None
    if ph:
        category_hint = ph
    else:
        for w in BASE_PRODUCT_WORDS:
            if re.search(rf"\b{re.escape(w)}\b", text):
                category_hint = w
                break

    must_terms: List[str] = []
    should_terms: List[str] = []

    # CP variants (cimento)
    for m in re.findall(r"\bcp\s*(iii|iv|ii|i|3|4|2|1)\b", text):
        token = _normalize_cp(f"cp {m}")
        if token and token not in must_terms:
            must_terms.append(token)

    # AC variants (argamassa)
    for m in re.findall(r"\bac\s*(iii|ii|3|2)\b", text):
        token = _normalize_ac(f"ac {m}")
        if token and token not in must_terms:
            must_terms.append(token)

    # Tijolo 8 furos
    if "tijolo" in text and "8 furos" in text and "8 furos" not in must_terms:
        must_terms.append("8 furos")

    # Cimento branco
    if "cimento branco" in text and "cimento branco" not in must_terms:
        must_terms.append("cimento branco")

    # known_context -> should_terms
    ctx_keys = [
        "application",
        "environment",
        "exposure",
        "load_type",
        "surface",
        "grain",
        "size",
        "argamassa_type",
    ]
    for k in ctx_keys:
        v = known_context.get(k)
        if not v:
            continue
        v_norm = norm(str(v))
        if v_norm and v_norm not in should_terms:
            should_terms.append(v_norm)

    strict = bool(must_terms)

    return {
        "category_hint": category_hint or None,
        "must_terms": must_terms,
        "should_terms": should_terms,
        "exclude_categories": [],
        "strict": strict,
    }
