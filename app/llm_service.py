"""
Serviço de LLM (Groq) para interpretação semântica e síntese técnica.

Responsabilidades:
- Interpretar escolhas naturais do usuário ("sim, a 2", "essa segunda")
- Gerar síntese técnica contextual baseada em fatores coletados
"""
import os
import json
import logging
from typing import Optional, Dict, List, Any
from groq import Groq
from app import settings


# Cliente Groq (singleton)
_groq_client = None

_ROUTER_INTENTS = {
    "BROWSE_CATALOG",
    "FIND_PRODUCT",
    "TECHNICAL_QUESTION",
    "ADD_TO_CART",
    "REMOVE_ITEM",
    "CHECKOUT",
    "PAYMENT",
    "ORDER_STATUS",
    "SMALLTALK",
    "UNKNOWN",
}

_ROUTER_ACTIONS = {
    "SHOW_CATALOG",
    "SEARCH_PRODUCTS",
    "ASK_CLARIFYING_QUESTION",
    "ASK_USAGE_CONTEXT",
    "ANSWER_WITH_RAG",
    "HANDOFF_CHECKOUT",
    "NOOP",
}

_CONSULTIVE_ACTIONS = {
    "ASK_CONTEXT",
    "READY_TO_ANSWER",
    "ASK_CLARIFYING_QUESTION",
}

_RENDER_STYLES = {
    "NEUTRO",
    "VENDEDOR",
    "TECNICO",
    "CURTO_WHATSAPP",
}


def _get_groq_client() -> Groq:
    """Retorna cliente Groq (singleton)."""
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY não encontrada no .env")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def _redact_text(text: str) -> str:
    """Reduz risco de PII em logs."""
    if not text:
        return ""
    t = text
    import re
    t = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[email]", t)
    t = re.sub(r"\b\d{6,}\b", "[num]", t)
    t = re.sub(r"\b\d{2,3}\s*\d{4,5}-?\d{4}\b", "[phone]", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 120:
        t = t[:117] + "..."
    return t


def _parse_json_text(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    content = raw.strip()
    if content.startswith("```"):
        content = content.strip("`")
    content = content.strip()
    if "{" in content and "}" in content:
        content = content[content.find("{") : content.rfind("}") + 1]
    try:
        data = json.loads(content)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _validate_route_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    intent = payload.get("intent")
    action = payload.get("action")
    confidence_raw = payload.get("confidence", 0.0)

    if intent not in _ROUTER_INTENTS:
        return None
    if action not in _ROUTER_ACTIONS:
        return None
    try:
        confidence_val = float(confidence_raw)
    except Exception:
        confidence_val = 0.0
    confidence_val = max(0.0, min(1.0, confidence_val))

    product_query = payload.get("product_query", None)
    category_hint = payload.get("category_hint", None)
    constraints = payload.get("constraints", {})
    clarifying_question = payload.get("clarifying_question", None)

    if product_query is not None and not isinstance(product_query, str):
        return None
    if category_hint is not None and not isinstance(category_hint, str):
        return None
    if clarifying_question is not None and not isinstance(clarifying_question, str):
        return None
    if constraints is None:
        constraints = {}
    if not isinstance(constraints, dict):
        return None

    return {
        "intent": intent,
        "product_query": product_query,
        "category_hint": category_hint,
        "constraints": constraints,
        "action": action,
        "clarifying_question": clarifying_question,
        "confidence": confidence_val,
        "decision": intent,
        "reasons": payload.get("reasons"),
    }


def _validate_consultive_plan(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    next_action = payload.get("next_action")
    confidence_raw = payload.get("confidence", 0.0)

    if next_action not in _CONSULTIVE_ACTIONS:
        return None
    try:
        confidence_val = float(confidence_raw)
    except Exception:
        confidence_val = 0.0
    confidence_val = max(0.0, min(1.0, confidence_val))

    missing_fields = payload.get("missing_fields", [])
    next_question = payload.get("next_question", None)
    assumptions = payload.get("assumptions", [])

    if missing_fields is None:
        missing_fields = []
    if not isinstance(missing_fields, list) or not all(isinstance(x, str) for x in missing_fields):
        return None
    if next_question is not None and not isinstance(next_question, str):
        return None
    if assumptions is None:
        assumptions = []
    if not isinstance(assumptions, list) or not all(isinstance(x, str) for x in assumptions):
        return None

    return {
        "missing_fields": missing_fields,
        "next_action": next_action,
        "next_question": next_question,
        "assumptions": assumptions,
        "confidence": confidence_val,
        "decision": next_action,
        "reasons": payload.get("reasons"),
    }


def route_intent(message: str, state_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    LLM Router: classifica a intencao e retorna decisao estruturada em JSON.

    Retorna dict validado ou None em erro (para fallback do fluxo atual).
    """
    if not message or not isinstance(state_summary, dict):
        return None

    prompt = f"""Voce e um roteador LLM para um chatbot de materiais de construcao.

REGRAS ABSOLUTAS:
- NUNCA responda ao usuario, somente JSON valido
- NAO invente produtos
- NUNCA liste catalogo aqui

REGRA CRITICA PARA PRODUTOS GENERICOS:
- Se o usuario pedir cimento/tinta/areia/brita/argamassa SEM especificar uso/aplicacao:
  - Use action=ASK_USAGE_CONTEXT (SEMPRE)
  - Inclua clarifying_question perguntando o uso
- So use ANSWER_WITH_RAG se state_summary.consultive_context_missing estiver VAZIO

ROTEAMENTO:
- "que tipos tem / quais opcoes / tem X?" -> BROWSE_CATALOG + SHOW_CATALOG
- "quero X para Y" (com aplicacao) -> ASK_USAGE_CONTEXT (para coletar mais contexto)
- "quero X" (generico, sem aplicacao) -> ASK_USAGE_CONTEXT
- checkout/pagamento/orcamento -> HANDOFF_CHECKOUT
- incerto -> ASK_CLARIFYING_QUESTION ou NOOP

RETORNE SOMENTE ESTE JSON:
{{
  "intent": "BROWSE_CATALOG|FIND_PRODUCT|TECHNICAL_QUESTION|ADD_TO_CART|REMOVE_ITEM|CHECKOUT|PAYMENT|ORDER_STATUS|SMALLTALK|UNKNOWN",
  "product_query": "string ou null",
  "category_hint": "string ou null",
  "constraints": {{}},
  "action": "SHOW_CATALOG|SEARCH_PRODUCTS|ASK_CLARIFYING_QUESTION|ASK_USAGE_CONTEXT|ANSWER_WITH_RAG|HANDOFF_CHECKOUT|NOOP",
  "clarifying_question": "string ou null",
  "confidence": 0.0
}}

MENSAGEM DO USUARIO:
{message}

STATE_SUMMARY (json):
{json.dumps(state_summary, ensure_ascii=False)}
"""

    try:
        client = _get_groq_client()
        logging.info(
            "llm_router input_len=%s state_keys=%s msg=%s",
            len(message),
            list(state_summary.keys()),
            _redact_text(message),
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        raw = response.choices[0].message.content if response.choices else ""
        payload = _parse_json_text(raw)
        validated = _validate_route_payload(payload or {})
        if not validated:
            logging.info("llm_router invalid_json output=%s", _redact_text(str(raw)))
            return None

        logging.info(
            "llm_router output intent=%s action=%s confidence=%.2f product_query=%s",
            validated.get("intent"),
            validated.get("action"),
            float(validated.get("confidence", 0.0)),
            _redact_text(validated.get("product_query") or ""),
        )
        return validated
    except Exception as e:
        logging.info("llm_router error=%s", str(e)[:200])
        return None


def plan_consultive_next_step(
    message: str,
    state_summary: Dict[str, Any],
    product_hint: Optional[str],
    known_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Planner consultivo: decide proximo passo (perguntar contexto ou responder).

    Retorna dict validado ou None em erro (para fallback do fluxo atual).
    """
    if not message or not isinstance(state_summary, dict) or not isinstance(known_context, dict):
        return None

    prompt = f"""Voce e um planner consultivo para materiais de construcao.
Seu trabalho e decidir o proximo passo com base na pergunta e contexto.

REGRAS ABSOLUTAS:
- NUNCA liste produtos, catalogo, preco ou estoque
- NUNCA invente dados
- Responda SOMENTE com JSON valido
- Pergunte UMA pergunta curta por vez

REGRA CRITICA PARA READY_TO_ANSWER:
- CIMENTO/ARGAMASSA: so use READY_TO_ANSWER se known_context tiver application E environment
- TINTA: so use READY_TO_ANSWER se known_context tiver surface E environment
- Se known_context estiver vazio ou incompleto, use ASK_CONTEXT com missing_fields

CAMPOS OBRIGATORIOS POR PRODUTO:
- cimento: application, environment (minimo)
- tinta: surface, environment (minimo)
- areia/brita: application (minimo)

SCHEMA DE SAIDA:
{{
  "missing_fields": ["..."],
  "next_action": "ASK_CONTEXT|READY_TO_ANSWER|ASK_CLARIFYING_QUESTION",
  "next_question": "string ou null",
  "assumptions": ["..."],
  "confidence": 0.0
}}

MENSAGEM DO USUARIO:
{message}

PRODUCT_HINT:
{product_hint or ""}

KNOWN_CONTEXT (json):
{json.dumps(known_context, ensure_ascii=False)}

STATE_SUMMARY (json):
{json.dumps(state_summary, ensure_ascii=False)}
"""

    try:
        client = _get_groq_client()
        logging.info(
            "llm_planner input_len=%s product_hint=%s msg=%s",
            len(message),
            _redact_text(product_hint or ""),
            _redact_text(message),
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        raw = response.choices[0].message.content if response.choices else ""
        payload = _parse_json_text(raw)
        validated = _validate_consultive_plan(payload or {})
        if not validated:
            logging.info("llm_planner invalid_json output=%s", _redact_text(str(raw)))
            return None

        logging.info(
            "llm_planner output action=%s confidence=%.2f missing=%s",
            validated.get("next_action"),
            float(validated.get("confidence", 0.0)),
            validated.get("missing_fields"),
        )
        return validated
    except Exception as e:
        logging.info("llm_planner error=%s", str(e)[:200])
        return None


def _extract_fact_items(facts: Dict[str, Any]) -> List[Dict[str, str]]:
    items = facts.get("items") or facts.get("suggested_items") or []
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name") or it.get("nome")
        if not name:
            continue
        out.append(
            {
                "id": str(it.get("id") or it.get("product_id") or ""),
                "name": str(name),
                "price": str(it.get("price") or it.get("preco") or ""),
                "unit": str(it.get("unit") or it.get("unidade") or ""),
            }
        )
    return out


def _render_output_is_safe(text: str, facts: Dict[str, Any]) -> bool:
    if not text:
        return False
    if len(text) > 1200:
        return False
    if "http://" in text or "https://" in text:
        return False

    items = _extract_fact_items(facts)
    allowed_names = [it["name"].lower() for it in items if it.get("name")]
    allowed_prices = [it["price"] for it in items if it.get("price")]

    if "R$" in text and not any(p for p in allowed_prices if p in text):
        return False

    if allowed_names:
        for line in text.splitlines():
            line_l = line.lower().strip()
            if not line_l:
                continue
            is_list_like = False
            if line_l.startswith(("-", "*", "•")):
                is_list_like = True
            if line_l[:2].isdigit() and ")" in line_l[:4]:
                is_list_like = True
            if is_list_like and not any(name in line_l for name in allowed_names):
                return False

    return True


def render_customer_message(style: str, facts: Dict[str, Any]) -> Optional[str]:
    """
    Redator LLM: transforma facts em mensagem curta para WhatsApp.
    Retorna texto validado ou None em falha (para fallback).
    """
    if not isinstance(facts, dict):
        return None
    if style not in _RENDER_STYLES:
        style = "NEUTRO"

    facts_json = json.dumps(facts, ensure_ascii=False)

    prompt = f"""Voce e um redator de mensagens para WhatsApp (PT-BR).
Use SOMENTE as informacoes em FACTS. NUNCA invente.

REGRAS:
- Nao criar itens, precos, estoque, marcas, condicoes ou prazos.
- Se faltar informacao para responder, faca 1 pergunta curta.
- Mensagem curta, escaneavel (WhatsApp): frases curtas, bullets se necessario.
- Quando listar produtos, use exatamente os nomes/ids dos FACTS.
- Se FACTS tiver exact_match_found=false e unavailable_specs, diga que nao encontrou no catalogo.

ESTILO: {style}

FACTS (json):
{facts_json}

Retorne apenas o texto da mensagem (sem JSON, sem markdown extra).
"""

    try:
        client = _get_groq_client()
        logging.info(
            "llm_render input type=%s style=%s",
            _redact_text(str(facts.get("type", ""))),
            style,
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=250,
        )
        raw = response.choices[0].message.content if response.choices else ""
        text = (raw or "").strip().strip("`").strip()
        if text.startswith("{") and text.endswith("}"):
            return None
        if not _render_output_is_safe(text, facts):
            logging.info("llm_render unsafe_output=%s", _redact_text(text))
            return None
        return text
    except Exception as e:
        logging.info("llm_render error=%s", str(e)[:200])
        return None


def maybe_render_customer_message(style: str, facts: Dict[str, Any]) -> Optional[str]:
    if not settings.LLM_RENDERING_ENABLED:
        logging.info("llm_render skipped feature_flag=off")
        return None
    rendered = render_customer_message(style, facts)
    if rendered:
        logging.info("llm_render success")
        return rendered
    logging.info("llm_render fallback")
    return None


def interpret_choice(
    user_message: str,
    options: List[Dict[str, Any]],
    max_retries: int = 2
) -> Optional[int]:
    """
    Interpreta escolha natural do usuário usando LLM.

    Args:
        user_message: Mensagem do usuário (ex: "sim, a 2", "essa segunda")
        options: Lista de opções exibidas [{"id": 123, "nome": "Cimento CP II"}]
        max_retries: Número máximo de tentativas

    Returns:
        Índice 1-based da opção escolhida ou None se não identificado

    Examples:
        >>> interpret_choice("sim, a 2", [...])
        2
        >>> interpret_choice("quero essa primeira", [...])
        1
        >>> interpret_choice("pode ser a terceira", [...])
        3
    """
    if not user_message or not options:
        return None

    # Monta prompt
    options_text = "\n".join([
        f"{idx+1}) {opt.get('nome', 'Produto')}"
        for idx, opt in enumerate(options)
    ])

    prompt = f"""Você é um assistente que interpreta escolhas de produtos em um catálogo.

CATÁLOGO EXIBIDO:
{options_text}

MENSAGEM DO USUÁRIO:
"{user_message}"

TAREFA:
Identifique qual produto o usuário está escolhendo. O usuário pode:
- Usar número direto: "2", "o 2", "a 2"
- Usar posição: "primeira", "segunda", "terceira"
- Usar demonstrativos: "essa", "esse", "esta"
- Adicionar palavras: "sim, a 2", "quero essa primeira", "pode ser a 3"

RESPOSTA:
Retorne APENAS o número do produto (1, 2, 3...) ou "NENHUM" se não identificar escolha clara.

Exemplos:
- "sim, a 2" → 2
- "essa segunda" → 2
- "quero o primeiro" → 1
- "pode ser essa" → NENHUM (ambíguo)
- "não sei" → NENHUM
"""

    try:
        client = _get_groq_client()

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Baixa temperatura para escolha precisa
            max_tokens=10,
        )

        result = response.choices[0].message.content.strip()

        # Tenta extrair número
        if result.upper() == "NENHUM":
            return None

        # Extrai número da resposta
        import re
        nums = re.findall(r"\d+", result)
        if nums:
            choice_num = int(nums[0])
            # Valida range
            if 1 <= choice_num <= len(options):
                return choice_num

        return None

    except Exception as e:
        print(f"[WARN] LLM interpret_choice falhou: {e}")
        return None


def generate_technical_synthesis(
    product_category: str,
    context: Dict[str, Any],
    technical_factors: List[str]
) -> str:
    """
    Gera síntese técnica contextual usando LLM.

    IMPORTANTE: Só deve ser chamada com contexto COMPLETO (validado por can_generate_technical_answer).

    Args:
        product_category: Categoria do produto (cimento, tinta, areia, brita, argamassa)
        context: Contexto coletado {"application": "laje", "environment": "externa", ...}
        technical_factors: Lista de fatores técnicos relevantes ["resistência a sulfatos", ...]

    Returns:
        Texto de síntese técnica (2-3 frases)

    Examples:
        >>> generate_technical_synthesis(
        ...     "cimento",
        ...     {"application": "laje", "environment": "externa", "exposure": "exposto", "load_type": "residencial"},
        ...     ["resistência a sulfatos", "durabilidade", "resistência mecânica"]
        ... )
        "Para laje externa exposta em uso residencial, o ideal é cimento com resistência a sulfatos..."
    """
    if not product_category or not context:
        return ""

    # BLOQUEIO DE SEGURANÇA DUPLO: Importa e usa gate central
    # Esta é uma proteção ADICIONAL caso alguém chame esta função diretamente
    from app.flows.technical_recommendations import can_generate_technical_answer

    if not can_generate_technical_answer(product_category, context):
        print(f"[BLOCK] generate_technical_synthesis BLOQUEADA pelo gate. Produto: {product_category}, Contexto: {context}")
        return ""

    # Validação mínima: para tinta, aceitar surface+environment; demais exigem application
    prod_l = product_category.lower()
    if "tinta" in prod_l:
        if not context.get("surface") or not context.get("environment"):
            print(f"[WARN] generate_technical_synthesis tinta sem surface/environment. Produto: {product_category}")
            return ""
    else:
        if not context.get("application"):
            print(f"[WARN] generate_technical_synthesis chamada sem 'application' no contexto. Produto: {product_category}")
            return ""

    # Monta contexto legível
    context_items = []
    if context.get("application"):
        context_items.append(f"Aplicação: {context['application']}")
    if context.get("environment"):
        context_items.append(f"Ambiente: {context['environment']}")
    if context.get("exposure"):
        context_items.append(f"Exposição: {context['exposure']}")
    if context.get("load_type"):
        context_items.append(f"Tipo de carga: {context['load_type']}")
    if context.get("surface"):
        context_items.append(f"Superfície: {context['surface']}")
    if context.get("grain"):
        context_items.append(f"Granulometria: {context['grain']}")
    if context.get("size"):
        context_items.append(f"Tamanho: {context['size']}")

    context_text = "\n".join(context_items) if context_items else "Contexto não especificado"
    factors_text = ", ".join(technical_factors) if technical_factors else "fatores padrão"

    prompt = f"""Voce e um vendedor tecnico de materiais de construcao. Seja direto e tecnico.

REGRA ABSOLUTA - ANTI-ALUCINACAO:
- Use APENAS as informacoes do CONTEXTO COLETADO abaixo
- NUNCA invente ambiente, exposicao, carga ou qualquer dado nao listado
- Se o contexto tiver apenas "Aplicacao", mencione APENAS a aplicacao
- NAO copie os exemplos - eles sao apenas formato

PRODUTO: {product_category}

CONTEXTO COLETADO (use SOMENTE isto):
{context_text}

FATORES TECNICOS:
{factors_text}

TAREFA:
Gere 2-3 frases curtas explicando por que esse produto faz sentido para o contexto EXATO acima.

FORMATO:
"Para [aplicacao EXATA do contexto], o ideal e [tipo] porque [razao]. [Beneficio]."

Gere a explicacao (2-3 frases, sem inventar dados):"""

    try:
        client = _get_groq_client()

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Baixa temperatura para consistência técnica
            max_tokens=200,
        )

        synthesis = response.choices[0].message.content.strip()

        # Remove aspas se houver
        synthesis = synthesis.strip('"').strip("'")

        return synthesis

    except Exception as e:
        print(f"[WARN] LLM generate_technical_synthesis falhou: {e}")
        # Fallback genérico
        if context.get("application"):
            return f"Para {context['application']}, considere os fatores técnicos relevantes para garantir a melhor escolha."
        return "Considere os fatores técnicos relevantes para sua aplicação."


def extract_product_factors(product_category: str) -> List[str]:
    """
    Retorna lista de fatores técnicos relevantes para cada categoria.

    Args:
        product_category: Categoria do produto

    Returns:
        Lista de fatores técnicos
    """
    # Mapeamento de fatores por categoria
    CATEGORY_FACTORS = {
        "cimento": [
            "resistência a sulfatos",
            "resistência mecânica",
            "durabilidade",
            "resistência à umidade",
            "tempo de pega",
            "trabalhabilidade"
        ],
        "tinta": [
            "resistência à umidade",
            "resistência UV (sol)",
            "lavabilidade",
            "cobertura",
            "acabamento",
            "aderência ao substrato"
        ],
        "areia": [
            "granulometria",
            "trabalhabilidade",
            "acabamento superficial",
            "resistência mecânica da mistura"
        ],
        "brita": [
            "tamanho das pedras",
            "compactação",
            "resistência mecânica",
            "drenagem"
        ],
        "argamassa": [
            "aderência",
            "trabalhabilidade",
            "tempo de uso",
            "resistência mecânica"
        ]
    }

    # Busca fatores
    for key, factors in CATEGORY_FACTORS.items():
        if key in product_category.lower():
            return factors

    # Fallback genérico
    return ["qualidade", "durabilidade", "aplicação adequada"]
