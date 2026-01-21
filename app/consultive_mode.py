"""
Modo consultivo: responde perguntas abertas usando RAG + conhecimento da base.

Exemplos:
- "Esse produto serve pra laje?"
- "Posso usar isso em área externa?"
- "Qual é melhor pra banheiro?"
"""
from typing import Tuple, List, Dict, Any
from sqlalchemy.orm import Session

from app.rag_products import search_products_semantic
from app.text_utils import norm, BASE_PRODUCT_WORDS
from app.product_search import format_options
from database import SessionLocal, Produto


def _extract_product_keyword(question: str) -> str:
    t = norm(question)
    if not t:
        return ""
    for tok in t.split():
        if tok in BASE_PRODUCT_WORDS:
            return tok
    return ""


def _sql_find_products_by_keyword(keyword: str, k: int = 6) -> List[Dict[str, Any]]:
    db: Session = SessionLocal()
    try:
        q = (keyword or "").strip()
        if len(q) < 2:
            return []

        rows = (
            db.query(Produto)
            .filter(Produto.ativo == True, Produto.nome.ilike(f"%{q}%"))  # noqa: E712
            .limit(k)
            .all()
        )

        out: List[Dict[str, Any]] = []
        for p in rows:
            out.append(
                {
                    "id_produto": int(p.id),
                    "nome": p.nome,
                    "unidade": (p.unidade or "UN").strip(),
                    "preco": float(p.preco) if p.preco is not None else 0.0,
                    "estoque": float(p.estoque_atual) if p.estoque_atual is not None else 0.0,
                    "score": 0.80,
                }
            )
        return out
    finally:
        db.close()


def _is_type_question(question: str) -> bool:
    t = norm(question)
    return any(
        phrase in t
        for phrase in [
            "que tipo",
            "que tipos",
            "quais tipos",
            "tipos de",
            "tem que tipo",
            "tem tipos",
            "tem tipo",
        ]
    )


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

    product_keyword = _extract_product_keyword(question)

    # Extrai contexto da pergunta (produto mencionado)
    query = question
    if context_product:
        query = f"{context_product} {question}"

    # Prioriza busca SQL ancorada no produto para evitar "alucinação" do RAG
    products = _sql_find_products_by_keyword(product_keyword, k=6) if product_keyword else []
    if not products:
        # Busca produtos relevantes no RAG (threshold baixo para perguntas)
        products = search_products_semantic(query, k=3, min_relevance=0.25)

    # Filtro leve: se houve palavra-chave, mantém apenas itens que contenham a palavra no nome
    if product_keyword and products:
        filtered = [p for p in products if product_keyword in norm(p.get("nome", ""))]
        if filtered:
            products = filtered

    if not products:
        # Não encontrou nada relevante
        return (
            "Não encontrei informações específicas sobre isso no meu catálogo. "
            "Posso te ajudar a encontrar um produto? Me diga o que você precisa.",
            False
        )

    # Resposta direta para "que tipos de X tem?"
    if product_keyword and products and _is_type_question(question):
        response = (
            f"Temos estes tipos de **{product_keyword}** no catálogo:\n\n"
            f"{format_options(products)}\n\n"
            "Quer que eu te ajude a escolher e comprar?"
        )
        return response, needs_human

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
        try:
            p1_ok = float(preco1) > 0
            p2_ok = float(preco2) > 0
        except Exception:
            p1_ok = p2_ok = False

        if p1_ok and p2_ok:
            if preco1 > preco2 * 1.2:
                diferenca = f"{n1} tem um custo maior que {n2}."
            elif preco2 > preco1 * 1.2:
                diferenca = f"{n2} tem um custo maior que {n1}."
            else:
                diferenca = f"Ambos têm preços similares."

        if diferenca:
            return f"Temos {n1} e {n2} disponíveis. {diferenca} Qual você prefere?"
        return f"Temos {n1} e {n2} disponíveis. Qual deles parece atender melhor o que você precisa?"
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
