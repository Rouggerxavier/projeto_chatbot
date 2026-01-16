"""
Modo consultivo: responde perguntas abertas usando RAG + conhecimento da base.

Exemplos:
- "Esse produto serve pra laje?"
- "Posso usar isso em área externa?"
- "Qual é melhor pra banheiro?"
"""
from typing import Tuple
from app.rag_products import search_products_semantic
from app.text_utils import norm


def answer_consultive_question(question: str, context_product: str = None) -> Tuple[str, bool]:
    """
    Responde pergunta consultiva usando RAG.

    Args:
        question: Pergunta do usuário
        context_product: Produto mencionado anteriormente (opcional)

    Returns:
        (resposta, needs_human): resposta gerada + flag se precisa humano
    """
    needs_human = False

    # Extrai contexto da pergunta (produto mencionado)
    query = question
    if context_product:
        query = f"{context_product} {question}"

    # Busca produtos relevantes no RAG (threshold baixo para perguntas)
    products = search_products_semantic(query, k=3, min_relevance=0.25)

    if not products:
        # Não encontrou nada relevante
        return (
            "Não encontrei informações específicas sobre isso no meu catálogo. "
            "Posso te ajudar a encontrar um produto? Me diga o que você precisa.",
            False
        )

    # Analisa a pergunta
    q_norm = norm(question)

    # Perguntas sobre aplicação/uso
    if any(x in q_norm for x in ["serve", "usar", "aplica", "uso", "funciona", "pode"]):
        response = _answer_usage_question(products, question)

    # Perguntas comparativas
    elif any(x in q_norm for x in ["qual", "melhor", "diferenca", "comparar"]):
        response = _answer_comparison_question(products, question)

    # Perguntas sobre características
    elif any(x in q_norm for x in ["e bom", "e boa", "qualidade", "resistente", "duravel"]):
        response = _answer_quality_question(products, question)

    # Genérica
    else:
        response = _answer_generic_question(products, question)

    # Adiciona convite para compra (natural, não forçado)
    if len(products) == 1:
        prod = products[0]
        nome = prod.get("nome", "")
        preco = prod.get("preco", 0.0)
        unidade = prod.get("unidade", "UN")
        response += f"\n\nTemos {nome} disponível (R$ {preco:.2f}/{unidade}). Quer adicionar ao carrinho?"
    else:
        response += "\n\nQuer que eu te ajude a escolher e comprar?"

    return response, needs_human


def _answer_usage_question(products, question):
    """Responde perguntas sobre uso/aplicação."""
    if len(products) == 1:
        prod = products[0]
        nome = prod.get("nome", "")
        # Resposta baseada em conhecimento geral (sem inventar)
        return f"{nome} é indicado para construção civil. Para aplicações específicas, recomendo verificar a ficha técnica do fabricante."
    else:
        nomes = [p.get("nome", "") for p in products[:2]]
        return f"Temos {nomes[0]} e {nomes[1]} que podem atender. Qual tipo de aplicação você precisa?"


def _answer_comparison_question(products, question):
    """Responde perguntas comparativas."""
    if len(products) >= 2:
        p1, p2 = products[0], products[1]
        n1, n2 = p1.get("nome", ""), p2.get("nome", "")
        preco1, preco2 = p1.get("preco", 0.0), p2.get("preco", 0.0)

        diferenca = ""
        if preco1 > preco2 * 1.2:
            diferenca = f"{n1} tem um custo maior que {n2}."
        elif preco2 > preco1 * 1.2:
            diferenca = f"{n2} tem um custo maior que {n1}."
        else:
            diferenca = f"Ambos têm preços similares."

        return f"Temos {n1} e {n2} disponíveis. {diferenca} Qual você prefere?"
    else:
        return "Temos esse produto disponível. Me diga mais sobre o que você precisa para te ajudar melhor."


def _answer_quality_question(products, question):
    """Responde perguntas sobre qualidade/características."""
    prod = products[0]
    nome = prod.get("nome", "")
    return f"{nome} é um produto do nosso catálogo. Para detalhes técnicos específicos, recomendo consultar a ficha do fabricante. Quer saber mais alguma coisa?"


def _answer_generic_question(products, question):
    """Resposta genérica quando não identifica o tipo de pergunta."""
    if len(products) == 1:
        prod = products[0]
        nome = prod.get("nome", "")
        return f"Sobre {nome}, posso te ajudar com informações de preço, estoque e disponibilidade. O que você gostaria de saber?"
    else:
        nomes = ", ".join([p.get("nome", "") for p in products[:2]])
        return f"Encontrei alguns produtos relacionados: {nomes}. Me diga mais sobre o que você precisa."
