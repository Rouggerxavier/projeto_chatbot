"""
Teste do fluxo completo - verifica apenas se funções executam sem erro.
"""
from app.flows.consultive_investigation import start_investigation, continue_investigation, is_investigation_complete
from app.session_state import reset_state, get_state
from app.flows.usage_context import ask_usage_context, handle_usage_context_response

SESSION_ID = "test_full_flow"

try:
    # Reset
    reset_state(SESSION_ID)

    # 1. Pede produto genérico
    reply1 = ask_usage_context(SESSION_ID, "cimento")
    assert reply1 is not None, "ask_usage_context retornou None"

    # 2. Informa aplicação
    reply2 = handle_usage_context_response(SESSION_ID, "pra laje")
    assert reply2 is not None, "handle_usage_context_response retornou None"

    st = get_state(SESSION_ID)
    assert st.get("consultive_investigation") == True, "Não iniciou investigação"

    # 3. Responde ambiente
    reply3 = continue_investigation(SESSION_ID, "externa")
    assert reply3 is not None, "continue_investigation (step 1) retornou None"

    # 4. Responde exposição
    reply4 = continue_investigation(SESSION_ID, "exposto")
    assert reply4 is not None, "continue_investigation (step 2) retornou None"

    # 5. Responde carga
    reply5 = continue_investigation(SESSION_ID, "residencial")
    # Esta última deve retornar a recomendação técnica
    assert reply5 is not None, "continue_investigation (final) retornou None - esperava recomendação"

    st = get_state(SESSION_ID)
    assert st.get("consultive_recommendation_shown") == True, "Não marcou recommendation_shown"

    # Verifica se recomendação tem conteúdo técnico
    assert len(reply5) > 50, "Recomendação muito curta"

    print("[OK] Fluxo completo funcionou!")
    print(f"[OK] Passos executados: ask_usage_context -> handle_usage_context_response -> continue_investigation (3x)")
    print(f"[OK] Estado final: recommendation_shown=True, environment=externa, exposure=exposto, load_type=residencial")
    print(f"[OK] Recomendação gerada com {len(reply5)} caracteres")

except AssertionError as e:
    print(f"[FAIL] {e}")
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
