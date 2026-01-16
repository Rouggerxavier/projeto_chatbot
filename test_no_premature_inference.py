"""
Teste de bloqueio de inferência prematura.

OBJETIVO:
Validar que o bot NUNCA infere contexto técnico sem coletar informações mínimas.

EXEMPLO DO PROBLEMA (NÃO DEVE MAIS ACONTECER):
    User: "quero cimento"
    Bot: "Para reboco externo exposto em área residencial..." ❌ ERRADO

COMPORTAMENTO CORRETO ESPERADO:
    User: "quero cimento"
    Bot: "É pra qual uso?" ✅ PERGUNTA

    User: "pra laje"
    Bot: "É área interna ou externa?" ✅ PERGUNTA

    User: "externa"
    Bot: "Coberta ou exposta?" ✅ PERGUNTA

    User: "exposta"
    Bot: "Uso residencial ou carga pesada?" ✅ PERGUNTA

    User: "residencial"
    Bot: [Agora sim, pode gerar síntese técnica] ✅ RESPOSTA TÉCNICA
"""
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.flow_controller import handle_message
from app.session_state import get_state
from app.flows.technical_recommendations import _validate_minimum_context
from database import SessionLocal, ChatSessionState


def limpar_sessao(session_ids):
    """Limpa estado antes de cada teste."""
    db = SessionLocal()
    try:
        for sid in session_ids:
            db.query(ChatSessionState).filter(ChatSessionState.user_id == sid).delete()
        db.commit()
    finally:
        db.close()


def test_cimento_generico_sem_inferencia():
    """
    Valida que "quero cimento" NÃO gera síntese técnica prematura.
    """
    session_id = "test_no_inference"
    limpar_sessao([session_id])

    print("\n" + "="*70)
    print("TESTE 1: 'quero cimento' não deve inferir contexto")
    print("="*70)

    # Passo 1: Usuário pede cimento (genérico)
    reply, _ = handle_message("quero cimento", session_id)

    # Validações:
    # 1. NÃO deve conter termos técnicos (externo, exposto, residencial, etc.)
    forbidden_terms = [
        "reboco externo",
        "exposto",
        "área residencial",
        "resistente a sulfatos",
        "cp iii",
        "cp iv",
        "laje externa",
    ]

    for term in forbidden_terms:
        if term.lower() in reply.lower():
            print(f"❌ FALHA: Bot inferiu '{term}' prematuramente!")
            print(f"Reply: {reply}")
            return False

    # 2. DEVE conter pergunta sobre uso
    if "uso" not in reply.lower() and "qual" not in reply.lower():
        print(f"❌ FALHA: Bot não perguntou sobre uso!")
        print(f"Reply: {reply}")
        return False

    print(f"✅ SUCESSO: Bot perguntou sobre uso (não inferiu)")
    print(f"Reply: {reply}")
    return True


def test_cimento_progressivo_completo():
    """
    Valida que a investigação progressiva funciona corretamente até o fim.
    """
    session_id = "test_progressive"
    limpar_sessao([session_id])

    print("\n" + "="*70)
    print("TESTE 2: Investigação progressiva completa")
    print("="*70)

    # Passo 1: "quero cimento"
    print("\n[Usuário] quero cimento")
    reply1, _ = handle_message("quero cimento", session_id)
    print(f"[Bot] {reply1[:150]}...")

    if "uso" not in reply1.lower() and "qual" not in reply1.lower():
        print("❌ FALHA: Não perguntou sobre uso")
        return False
    print("✅ Passo 1: OK")

    # Passo 2: "pra laje"
    print("\n[Usuário] pra laje")
    reply2, _ = handle_message("pra laje", session_id)
    print(f"[Bot] {reply2[:150]}...")

    if "interna" not in reply2.lower() and "externa" not in reply2.lower():
        print(f"❌ FALHA: Bot não perguntou ambiente!")
        return False
    print("✅ Passo 2: OK")

    # Passo 3: "externa"
    print("\n[Usuário] externa")
    reply3, _ = handle_message("externa", session_id)
    print(f"[Bot] {reply3[:150]}...")

    if "coberto" not in reply3.lower() and "exposto" not in reply3.lower():
        print(f"❌ FALHA: Bot não perguntou exposição!")
        return False
    print("✅ Passo 3: OK")

    # Passo 4: "exposta"
    print("\n[Usuário] exposta")
    reply4, _ = handle_message("exposta", session_id)
    print(f"[Bot] {reply4[:150]}...")

    if "residencial" not in reply4.lower() and "carga" not in reply4.lower():
        print(f"❌ FALHA: Bot não perguntou carga!")
        return False
    print("✅ Passo 4: OK")

    # Passo 5: "residencial"
    print("\n[Usuário] residencial")
    reply5, _ = handle_message("residencial", session_id)
    print(f"[Bot] {reply5[:300]}...")

    # AGORA SIM pode conter síntese técnica
    # Deve conter produtos ou catálogo
    if "1)" in reply5 or "cp" in reply5.lower():
        print("✅ Passo 5: Síntese técnica gerada corretamente")
    else:
        print("⚠️ Passo 5: Resposta genérica (sem LLM), mas ok")

    # Valida estado final
    st = get_state(session_id)
    if st.get("consultive_application") != "laje":
        print(f"❌ FALHA: Estado 'application' incorreto: {st.get('consultive_application')}")
        return False

    if st.get("consultive_environment") not in ["externa", "externo"]:
        print(f"❌ FALHA: Estado 'environment' incorreto: {st.get('consultive_environment')}")
        return False

    print("✅ Investigação progressiva completa!")
    return True


def test_validate_minimum_context_funciona():
    """
    Testa a função _validate_minimum_context diretamente.
    """
    print("\n" + "="*70)
    print("TESTE 3: Validação de contexto mínimo")
    print("="*70)

    tests_passed = 0
    tests_total = 0

    # Teste 1: Cimento com aplicação + ambiente → válido
    tests_total += 1
    context1 = {"product": "cimento", "application": "laje", "environment": "externa"}
    if _validate_minimum_context("cimento", context1) == True:
        print("✅ Contexto cimento válido (laje + externa)")
        tests_passed += 1
    else:
        print("❌ Contexto cimento deveria ser válido (laje + externa)")

    # Teste 2: Cimento com apenas aplicação "reboco" → válido (exceção)
    tests_total += 1
    context2 = {"product": "cimento", "application": "reboco"}
    if _validate_minimum_context("cimento", context2) == True:
        print("✅ Contexto cimento válido (reboco sem ambiente, exceção)")
        tests_passed += 1
    else:
        print("❌ Contexto cimento deveria ser válido (reboco é exceção)")

    # Teste 3: Cimento com apenas aplicação "laje" (sem ambiente) → inválido
    tests_total += 1
    context3 = {"product": "cimento", "application": "laje"}
    if _validate_minimum_context("cimento", context3) == False:
        print("✅ Contexto cimento inválido (laje sem ambiente)")
        tests_passed += 1
    else:
        print("❌ Contexto cimento deveria ser inválido (laje precisa ambiente)")

    # Teste 4: Cimento sem aplicação → inválido
    tests_total += 1
    context4 = {"product": "cimento"}
    if _validate_minimum_context("cimento", context4) == False:
        print("✅ Contexto cimento inválido (sem aplicação)")
        tests_passed += 1
    else:
        print("❌ Contexto cimento deveria ser inválido (sem aplicação)")

    # Teste 5: Tinta com superfície + ambiente → válido
    tests_total += 1
    context5 = {"product": "tinta", "surface": "parede", "environment": "externa"}
    if "application" in context5:
        print("X Contexto tinta nao deve exigir application")
        return False
    if _validate_minimum_context("tinta", context5) == True:
        print("✅ Contexto tinta válido (parede + externa)")
        tests_passed += 1
    else:
        print("❌ Contexto tinta deveria ser válido (parede + externa)")

    # Teste 6: Tinta sem ambiente → inválido
    tests_total += 1
    context6 = {"product": "tinta", "surface": "parede"}
    if _validate_minimum_context("tinta", context6) == False:
        print("✅ Contexto tinta inválido (sem ambiente)")
        tests_passed += 1
    else:
        print("❌ Contexto tinta deveria ser inválido (sem ambiente)")

    print(f"\nResultado: {tests_passed}/{tests_total} testes passaram")
    return tests_passed == tests_total


def test_cimento_50kg_sem_bypass():
    """
    Valida que "quero 50kg de cimento" também pede contexto (não bypasseia).
    """
    session_id = "test_50kg"
    limpar_sessao([session_id])

    print("\n" + "="*70)
    print("TESTE 4: '50kg de cimento' não deve bypasear investigação")
    print("="*70)

    print("\n[Usuário] quero 50kg de cimento")
    reply, _ = handle_message("quero 50kg de cimento", session_id)
    print(f"[Bot] {reply}")

    # Deve perguntar sobre uso (mesmo com quantidade)
    if "uso" not in reply.lower() and "qual" not in reply.lower():
        print(f"❌ FALHA: Bot bypassou investigação com quantidade!")
        return False

    # NÃO deve mostrar catálogo direto
    if "1)" in reply or "2)" in reply:
        print(f"❌ FALHA: Bot mostrou catálogo sem investigar!")
        return False

    print(f"✅ SUCESSO: '50kg de cimento' também pede contexto")
    return True


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("\n" + "#"*70)
    print("# TESTES DE BLOQUEIO DE INFERÊNCIA PREMATURA")
    print("#"*70)

    results = []

    # Executa testes
    results.append(("Validação contexto mínimo", test_validate_minimum_context_funciona()))
    results.append(("Cimento genérico sem inferência", test_cimento_generico_sem_inferencia()))
    results.append(("50kg cimento sem bypass", test_cimento_50kg_sem_bypass()))
    results.append(("Investigação progressiva completa", test_cimento_progressivo_completo()))

    # Sumário
    print("\n" + "#"*70)
    print("# SUMÁRIO")
    print("#"*70)

    passed = 0
    failed = 0
    for name, result in results:
        if result:
            print(f"✅ {name}")
            passed += 1
        else:
            print(f"❌ {name}")
            failed += 1

    print(f"\nTotal: {passed} passaram, {failed} falharam")

    if failed == 0:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        exit(0)
    else:
        print(f"\n⚠️ {failed} TESTE(S) FALHARAM")
        exit(1)
