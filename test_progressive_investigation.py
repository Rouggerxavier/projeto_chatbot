"""
Teste manual do fluxo de investigação progressiva.

Simula conversa completa:
User: "quero cimento"
Bot: "É pra qual uso?"
User: "pra laje"
Bot: "É área interna ou externa?"
User: "externa"
Bot: "É local coberto ou exposto?"
User: "exposto"
Bot: "É uso residencial ou carga pesada?"
User: "residencial"
Bot: [recomendação técnica + produtos]
User: "sim"
Bot: [lista produtos para escolha]
"""
from app.flows.usage_context import ask_usage_context, handle_usage_context_response
from app.flows.consultive_investigation import continue_investigation, is_investigation_complete
from app.session_state import get_state, patch_state, reset_state
from app.text_utils import norm

# Session de teste
SESSION_ID = "test_progressive_001"

print("=" * 80)
print("TESTE: INVESTIGAÇÃO PROGRESSIVA (MODO CONSULTIVO AVANÇADO)")
print("=" * 80)

# Reset estado
reset_state(SESSION_ID)

# Passo 1: Usuário pede produto genérico
print("\n[1] User: 'quero cimento'")
reply = ask_usage_context(SESSION_ID, "cimento")
print(f"    Bot: {reply}")

# Verifica estado
st = get_state(SESSION_ID)
print(f"    Estado: awaiting_usage_context={st.get('awaiting_usage_context')}")

# Passo 2: Usuário informa aplicação
print("\n[2] User: 'pra laje'")
reply = handle_usage_context_response(SESSION_ID, "pra laje")
print(f"    Bot: {reply}")

# Verifica estado
st = get_state(SESSION_ID)
print(f"    Estado: consultive_investigation={st.get('consultive_investigation')}, step={st.get('consultive_investigation_step')}, app={st.get('consultive_application')}")

# Passo 3: Investigação - pergunta 1 (ambiente)
print("\n[3] User: 'externa'")
reply = continue_investigation(SESSION_ID, "externa")
print(f"    Bot: {reply}")

# Verifica estado
st = get_state(SESSION_ID)
print(f"    Estado: step={st.get('consultive_investigation_step')}, environment={st.get('consultive_environment')}")

# Passo 4: Investigação - pergunta 2 (exposição)
print("\n[4] User: 'exposto'")
reply = continue_investigation(SESSION_ID, "exposto")
print(f"    Bot: {reply}")

# Verifica estado
st = get_state(SESSION_ID)
print(f"    Estado: step={st.get('consultive_investigation_step')}, exposure={st.get('consultive_exposure')}")

# Passo 5: Investigação - pergunta 3 (carga)
print("\n[5] User: 'residencial'")
reply = continue_investigation(SESSION_ID, "residencial")
print(f"    Bot: {reply}")

# Verifica estado
st = get_state(SESSION_ID)
print(f"    Estado: recommendation_shown={st.get('consultive_recommendation_shown')}, load_type={st.get('consultive_load_type')}")

# Verifica se investigação está completa
complete = is_investigation_complete(SESSION_ID)
print(f"    Investigação completa: {complete}")

print("\n" + "=" * 80)
print("VERIFICAÇÕES:")
print("=" * 80)

# Checklist
checks = [
    ("Perguntou aplicação", "É pra qual uso" in ask_usage_context(SESSION_ID, "cimento")),
    ("Iniciou investigação após aplicação", st.get("consultive_investigation") or st.get("consultive_recommendation_shown")),
    ("Coletou ambiente", st.get("consultive_environment") == "externa"),
    ("Coletou exposição", st.get("consultive_exposure") == "exposto"),
    ("Coletou tipo de carga", st.get("consultive_load_type") == "residencial"),
    ("Mostrou recomendação", st.get("consultive_recommendation_shown") == True),
    ("Recomendação tem explicação técnica", reply and ("CP" in reply or "resistente" in reply)),
    ("Tem validação passiva", reply and ("faz sentido" in reply.lower() or "fazem sentido" in reply.lower())),
]

passed = 0
failed = 0

for check_name, check_result in checks:
    if check_result:
        print(f"[OK] {check_name}")
        passed += 1
    else:
        print(f"[FAIL] {check_name}")
        failed += 1

print("\n" + "=" * 80)
print(f"RESULTADO: {passed} passou, {failed} falhou")
print("=" * 80)

if failed == 0:
    print("[OK] Todos os testes passaram!")
else:
    print(f"[FAIL] {failed} testes falharam.")
