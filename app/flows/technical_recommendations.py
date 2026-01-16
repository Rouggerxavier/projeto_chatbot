"""
Recomendações técnicas baseadas em contexto de aplicação.

Usa regras técnicas para recomendar produtos com explicação do porquê.

Exemplo:
    Contexto: cimento, laje, externa, exposta, residencial
    Recomendação:
        "Para laje externa exposta, o ideal é cimento resistente a sulfatos e umidade.

        **CP III** - resistente a sulfatos, ideal pra ambientes agressivos
        **CP IV** - alta durabilidade, ótimo para exposição contínua"
"""
from typing import Optional, Dict, List, Any, Tuple
from app.text_utils import norm
from app.product_search import format_options


# Regras técnicas por produto + contexto
TECHNICAL_RULES: Dict[str, Dict[Tuple, Dict[str, Any]]] = {
    "cimento": {
        # (aplicação, ambiente, exposição, carga)
        ("laje", "externa", "exposto", "residencial"): {
            "products": ["cp iii", "cp iv"],
            "reasoning": "Para laje externa exposta em área residencial, o ideal é cimento com resistência a sulfatos e umidade.",
            "options": [
                {"name": "CP III", "why": "resistente a sulfatos, ideal pra ambientes agressivos"},
                {"name": "CP IV", "why": "alta durabilidade, ótimo para exposição contínua"},
            ],
        },
        ("laje", "interna", None, "residencial"): {
            "products": ["cp ii", "cp iii"],
            "reasoning": "Para laje interna residencial, tanto CP II quanto CP III atendem bem.",
            "options": [
                {"name": "CP II", "why": "boa resistência estrutural, mais econômico"},
                {"name": "CP III", "why": "resistência extra, pega mais rápida"},
            ],
        },
        ("laje", "externa", "exposto", "pesado"): {
            "products": ["cp iii", "cp iv"],
            "reasoning": "Para laje com carga pesada em área externa, use cimento de alta resistência.",
            "options": [
                {"name": "CP III", "why": "resistente a sulfatos, boa resistência mecânica"},
                {"name": "CP IV", "why": "altíssima resistência, ideal pra carga pesada"},
            ],
        },
        ("fundacao", None, None, None): {
            "products": ["cp iii", "cp iv"],
            "reasoning": "Para fundação, o ideal é cimento resistente a sulfatos do solo.",
            "options": [
                {"name": "CP III", "why": "resistência a sulfatos, ideal pra fundações"},
                {"name": "CP IV", "why": "máxima durabilidade, resistência química"},
            ],
        },
        ("reboco", None, None, None): {
            "products": ["cp ii"],
            "reasoning": "Para reboco, CP II é a melhor escolha.",
            "options": [
                {"name": "CP II", "why": "boa trabalhabilidade, acabamento liso"},
            ],
        },
        ("piso", "interna", None, "residencial"): {
            "products": ["cp ii"],
            "reasoning": "Para contrapiso interno residencial, CP II funciona bem.",
            "options": [
                {"name": "CP II", "why": "boa resistência, ótimo custo-benefício"},
            ],
        },
        ("piso", "externa", None, None): {
            "products": ["cp iii"],
            "reasoning": "Para piso externo, use CP III para maior resistência.",
            "options": [
                {"name": "CP III", "why": "resiste bem a intempéries, durável"},
            ],
        },
    },
    "tinta": {
        # (superfície, ambiente)
        ("parede", "interna"): {
            "products": ["latex", "acrilica"],
            "reasoning": "Para parede interna, tintas látex e acrílica são ideais.",
            "options": [
                {"name": "Látex", "why": "lavável, ótima cobertura"},
                {"name": "Acrílica", "why": "mais resistente, melhor acabamento"},
            ],
        },
        ("parede", "externa"): {
            "products": ["acrilica", "textura"],
            "reasoning": "Para parede externa, prefira tintas resistentes ao tempo.",
            "options": [
                {"name": "Acrílica", "why": "resistente à chuva e sol"},
                {"name": "Textura", "why": "proteção extra, esconde imperfeições"},
            ],
        },
        ("madeira", None): {
            "products": ["esmalte", "verniz"],
            "reasoning": "Para madeira, use esmalte ou verniz para proteção.",
            "options": [
                {"name": "Esmalte", "why": "proteção total, várias cores"},
                {"name": "Verniz", "why": "mantém aspecto natural da madeira"},
            ],
        },
        ("metal", None): {
            "products": ["esmalte", "zarcao"],
            "reasoning": "Para metal, use esmalte sintético ou primer anticorrosivo.",
            "options": [
                {"name": "Esmalte sintético", "why": "proteção e acabamento"},
                {"name": "Zarcão", "why": "primer anticorrosivo, base antes da tinta"},
            ],
        },
    },
    "areia": {
        # (aplicação, granulometria)
        ("reboco", "fino"): {
            "products": ["areia fina"],
            "reasoning": "Para reboco com acabamento fino, use areia fina.",
            "options": [
                {"name": "Areia fina", "why": "acabamento liso, ideal pra reboco"},
            ],
        },
        ("reboco", "medio"): {
            "products": ["areia media"],
            "reasoning": "Para reboco comum, areia média funciona bem.",
            "options": [
                {"name": "Areia média", "why": "boa trabalhabilidade, mais econômica"},
            ],
        },
        ("assentamento", None): {
            "products": ["areia media"],
            "reasoning": "Para assentamento de tijolo/bloco, areia média é indicada.",
            "options": [
                {"name": "Areia média", "why": "liga bem, firmeza no assentamento"},
            ],
        },
        ("concreto", None): {
            "products": ["areia media", "areia grossa"],
            "reasoning": "Para concreto, areia média ou grossa funcionam bem.",
            "options": [
                {"name": "Areia média", "why": "padrão para concreto"},
                {"name": "Areia grossa", "why": "concreto mais resistente"},
            ],
        },
    },
    "brita": {
        # (aplicação, tamanho)
        ("concreto", "1"): {
            "products": ["brita 1"],
            "reasoning": "Para concreto estrutural, brita 1 é a mais usada.",
            "options": [
                {"name": "Brita 1", "why": "padrão pra concreto, boa compactação"},
            ],
        },
        ("concreto", "2"): {
            "products": ["brita 2"],
            "reasoning": "Para concreto com peças maiores, brita 2 funciona.",
            "options": [
                {"name": "Brita 2", "why": "pedras maiores, economia de cimento"},
            ],
        },
        ("drenagem", None): {
            "products": ["brita 3", "brita 4"],
            "reasoning": "Para drenagem, use britas maiores (3 ou 4).",
            "options": [
                {"name": "Brita 3", "why": "boa drenagem, espaços entre pedras"},
                {"name": "Brita 4", "why": "drenagem máxima, pedras grandes"},
            ],
        },
    },
}


def get_technical_recommendation(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Busca recomendação técnica baseada no contexto coletado.

    Args:
        context: Dicionário com aplicação, ambiente, exposição, etc.

    Returns:
        Dicionário com reasoning, options, products ou None
    """
    product = norm(context.get("product", ""))
    application = norm(context.get("application", ""))
    environment = norm(context.get("environment"))
    exposure = norm(context.get("exposure"))
    load_type = norm(context.get("load_type"))
    surface = norm(context.get("surface"))
    grain = norm(context.get("grain"))
    size = norm(context.get("size"))

    # Busca produto nas regras
    for product_key, rules in TECHNICAL_RULES.items():
        if product_key not in product:
            continue

        # Tenta match exato primeiro
        for rule_key, recommendation in rules.items():
            if _matches_rule(rule_key, {
                "application": application,
                "environment": environment,
                "exposure": exposure,
                "load_type": load_type,
                "surface": surface,
                "grain": grain,
                "size": size,
            }):
                return recommendation

        # Fallback: match parcial por aplicação
        for rule_key, recommendation in rules.items():
            if rule_key[0] and rule_key[0] in application:
                return recommendation

    return None


def _matches_rule(rule_key: Tuple, context: Dict[str, str]) -> bool:
    """
    Verifica se contexto bate com regra.

    Args:
        rule_key: Tupla da regra (aplicação, ambiente, exposição, etc.)
        context: Contexto coletado

    Returns:
        True se bate
    """
    # Regras podem ter None (qualquer valor)
    # Exemplo: ("laje", "externa", None, "residencial")
    # Bate com context = {"application": "laje", "environment": "externa", "load_type": "residencial"}

    if len(rule_key) == 2:
        # Formato curto (ex: tinta - superfície, ambiente)
        surface_match = rule_key[0] is None or rule_key[0] in context.get("surface", "")
        env_match = rule_key[1] is None or rule_key[1] in context.get("environment", "")
        return surface_match and env_match

    if len(rule_key) == 4:
        # Formato longo (ex: cimento - aplicação, ambiente, exposição, carga)
        app_match = rule_key[0] is None or rule_key[0] in context.get("application", "")
        env_match = rule_key[1] is None or rule_key[1] in context.get("environment", "")
        exp_match = rule_key[2] is None or rule_key[2] in context.get("exposure", "")
        load_match = rule_key[3] is None or rule_key[3] in context.get("load_type", "")
        return app_match and env_match and exp_match and load_match

    return False


def format_recommendation_text(rec: Dict[str, Any], products: List[Any], context: Dict[str, Any] = None) -> str:
    """
    Formata recomendação com explicação técnica (sem pressão).

    Args:
        rec: Dicionário de recomendação (reasoning, options)
        products: Lista de produtos do catálogo
        context: Contexto coletado (opcional) - usado para síntese técnica inteligente

    Returns:
        Texto formatado
    """
    if not rec:
        # Fallback genérico
        return f"Aqui estão as melhores opções:\n\n{format_options(products)}\n\nAlguma dessas faz sentido pra sua obra?"

    # NOVO: Usa LLM para gerar síntese técnica contextual se contexto disponível
    if context and context.get("product"):
        from app.llm_service import generate_technical_synthesis, extract_product_factors

        product_category = context.get("product", "")
        technical_factors = extract_product_factors(product_category)

        # Gera síntese técnica usando LLM
        synthesis = generate_technical_synthesis(
            product_category=product_category,
            context=context,
            technical_factors=technical_factors
        )

        # Usa síntese gerada pela LLM se disponível, senão usa reasoning hardcoded
        if synthesis:
            reply = f"{synthesis}\n\n"
        else:
            reply = f"{rec['reasoning']}\n\n"
    else:
        # Fallback: usa reasoning hardcoded
        reply = f"{rec['reasoning']}\n\n"

    # Opções técnicas
    for opt in rec.get("options", []):
        reply += f"**{opt['name']}** - {opt['why']}\n"

    reply += f"\n{format_options(products)}\n\n"

    # Validação passiva (sem pressão)
    reply += "Alguma dessas opções faz sentido pra sua obra?"

    return reply
