"""
Serviço de LLM (Groq) para interpretação semântica e síntese técnica.

Responsabilidades:
- Interpretar escolhas naturais do usuário ("sim, a 2", "essa segunda")
- Gerar síntese técnica contextual baseada em fatores coletados
"""
import os
import json
from typing import Optional, Dict, List, Any
from groq import Groq


# Cliente Groq (singleton)
_groq_client = None


def _get_groq_client() -> Groq:
    """Retorna cliente Groq (singleton)."""
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY não encontrada no .env")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


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

    prompt = f"""Você é um vendedor técnico especializado em materiais de construção. Fale como um vendedor experiente: direto, técnico mas acessível, sem enrolação.

PRODUTO: {product_category}

CONTEXTO COLETADO:
{context_text}

FATORES TÉCNICOS RELEVANTES:
{factors_text}

TAREFA:
Gere UMA explicação técnica curta (2-3 frases CURTAS) que:
1. Combine os principais fatores do contexto
2. Explique POR QUE esse produto faz sentido para ESSE contexto específico
3. Seja direto e objetivo - sem repetição ou enrolação
4. Use linguagem técnica mas acessível

FORMATO:
"Para [aplicação] em [ambiente/condições], o ideal é [tipo de produto] porque [razão técnica principal]. [Benefício específico]."

EXEMPLO CORRETO (cimento em laje externa exposta residencial):
"Para laje externa exposta em área residencial, o ideal é cimento resistente a sulfatos e umidade, porque essas condições exigem maior durabilidade contra agentes agressivos. Isso garante uma estrutura segura e duradoura."

EXEMPLO ERRADO (muito longo):
"Para laje externa exposta em área residencial, o ideal é cimento com alta resistência a sulfatos, resistência mecânica elevada, durabilidade garantida, resistência à umidade e tempo de pega adequado, pois essas condições climáticas exigem maior proteção contra agentes agressivos do ambiente, além de uma boa trabalhabilidade para garantir uma aplicação eficaz e uma estrutura segura e duradoura..."

Gere a explicação técnica (2-3 frases CURTAS):"""

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
