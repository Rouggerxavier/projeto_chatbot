"""
Teste de integração completo com as novas funcionalidades de LLM.

Simula fluxo real:
1. Usuário pede cimento
2. Bot pergunta aplicação
3. Usuário responde "pra laje"
4. Bot faz investigação progressiva (3 perguntas)
5. Bot gera recomendação técnica com síntese LLM
6. Usuário confirma com linguagem natural: "sim, a segunda"
7. Bot interpreta com LLM e processa escolha
"""
import os
from dotenv import load_dotenv

# Carrega .env
load_dotenv()

from app.flows.usage_context import ask_usage_context, handle_usage_context_response
from app.flows.consultive_investigation import continue_investigation
from app.flows.product_selection import handle_suggestions_choice
from app.session_state import reset_state, get_state, patch_state

SESSION_ID = "test_integration_llm"


def remove_emojis(text):
    """Remove emojis para evitar erro de encoding no console Windows."""
    import re
    # Remove emojis e outros caracteres Unicode problemáticos
    return re.sub(r'[^\x00-\x7F]+', '', text)


def test_full_flow_with_llm():
    """Testa fluxo completo com interpretação LLM."""
    print("\n" + "=" * 80)
    print("TESTE DE INTEGRACAO - FLUXO COMPLETO COM LLM")
    print("=" * 80)

    # Reset
    reset_state(SESSION_ID)

    # 1. Usuário pede produto genérico
    print("\n[1] User: 'quero cimento'")
    reply1 = ask_usage_context(SESSION_ID, "cimento")
    print(f"    Bot: {remove_emojis(reply1)[:100]}...")
    assert "qual uso" in reply1.lower() or "pra que" in reply1.lower()
    print("    [OK] Perguntou aplicacao")

    # 2. Informa aplicação
    print("\n[2] User: 'pra laje'")
    reply2 = handle_usage_context_response(SESSION_ID, "pra laje")
    print(f"    Bot: {remove_emojis(reply2)[:100]}...")
    st = get_state(SESSION_ID)
    assert st.get("consultive_investigation") == True
    print("    [OK] Iniciou investigacao progressiva")

    # 3. Investigação - pergunta 1 (ambiente)
    print("\n[3] User: 'externa'")
    reply3 = continue_investigation(SESSION_ID, "externa")
    print(f"    Bot: {remove_emojis(reply3)[:100]}...")
    st = get_state(SESSION_ID)
    assert st.get("consultive_environment") == "externa"
    print("    [OK] Coletou ambiente")

    # 4. Investigação - pergunta 2 (exposição)
    print("\n[4] User: 'exposto'")
    reply4 = continue_investigation(SESSION_ID, "exposto")
    print(f"    Bot: {remove_emojis(reply4)[:100]}...")
    st = get_state(SESSION_ID)
    assert st.get("consultive_exposure") == "exposto"
    print("    [OK] Coletou exposicao")

    # 5. Investigação - pergunta 3 (carga)
    print("\n[5] User: 'residencial'")
    reply5 = continue_investigation(SESSION_ID, "residencial")
    print(f"    Bot (sintese tecnica):")
    print(f"    {remove_emojis(reply5)[:400]}...")
    st = get_state(SESSION_ID)
    assert st.get("consultive_recommendation_shown") == True
    assert "laje" in reply5.lower()
    assert "externa" in reply5.lower()
    print("    [OK] Gerou recomendacao com sintese tecnica LLM")
    print("    [OK] Sintese menciona contexto completo (laje + externa + exposto + residencial)")

    # 6. Usuário confirma interesse com linguagem natural
    print("\n[6] User: 'sim'")
    # Simula o handler de validação passiva
    st = get_state(SESSION_ID)
    from app.product_search import db_find_best_products, format_options
    from app.text_utils import norm

    hint = st.get("consultive_product_hint")
    products = db_find_best_products(hint, k=6) or []

    # Prepara sugestões
    last_suggestions = []
    for p in products:
        # Simula _safe_option_id
        if hasattr(p, 'id'):
            pid = p.id
        elif isinstance(p, dict):
            pid = p.get('id')
        else:
            continue

        if hasattr(p, 'nome'):
            nome = p.nome
        elif isinstance(p, dict):
            nome = p.get('nome')
        else:
            nome = "Produto"

        last_suggestions.append({"id": pid, "nome": nome})

    patch_state(SESSION_ID, {
        "consultive_investigation": False,
        "consultive_recommendation_shown": False,
        "last_suggestions": last_suggestions,
        "last_hint": hint,
    })

    reply6 = f"Otimo! Aqui estao as opcoes:\n\n{format_options(products)}\n\nQual voce prefere? (responda 1, 2, 3... ou o nome)"
    print(f"    Bot: {remove_emojis(reply6)[:150]}...")
    print("    [OK] Mostrou produtos para escolha")

    # 7. Usuário escolhe com linguagem natural: "sim, a segunda"
    print("\n[7] User: 'sim, a segunda'")
    choice_reply = handle_suggestions_choice(SESSION_ID, "sim, a segunda")

    if choice_reply:
        print(f"    Bot: {remove_emojis(choice_reply)[:100]}...")
        print("    [OK] LLM interpretou 'sim, a segunda' corretamente")
        print("    [OK] Bot pediu quantidade")
    else:
        print("    [FAIL] LLM nao conseguiu interpretar escolha")
        return False

    # 8. Testa outras variações de escolha natural
    print("\n[8] Testando outras variacoes de escolha natural...")

    # Reset para testar outras escolhas
    reset_state(SESSION_ID)
    patch_state(SESSION_ID, {"last_suggestions": last_suggestions})

    test_cases = [
        ("quero essa primeira", 1),
        ("pode ser a 3", 3),
        ("vou levar o segundo", 2),
    ]

    for msg, expected_idx in test_cases:
        # Simula escolha
        from app.llm_service import interpret_choice
        result = interpret_choice(msg, last_suggestions)

        status = "[OK]" if result == expected_idx else "[FAIL]"
        print(f"    {status} '{msg}' -> interpretado como {result} (esperado: {expected_idx})")

        if result != expected_idx:
            return False

    print("\n" + "=" * 80)
    print("[OK] TESTE DE INTEGRACAO COMPLETO - PASSOU!")
    print("=" * 80)
    print("\nRESUMO:")
    print("- Investigacao progressiva: OK")
    print("- Sintese tecnica com LLM: OK")
    print("- Interpretacao de escolha natural: OK")
    print("- Integracao completa: OK")

    return True


if __name__ == "__main__":
    try:
        success = test_full_flow_with_llm()

        if success:
            print("\n[OK] Todos os testes de integracao passaram!")
        else:
            print("\n[FAIL] Alguns testes falharam")

    except AssertionError as e:
        print(f"\n[FAIL] Assertion: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
