"""
Teste simples de validacao de bloqueio de inferencia prematura.
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.flow_controller import handle_message
from app.session_state import get_state
from app.flows.technical_recommendations import _validate_minimum_context
from database import SessionLocal, ChatSessionState


def safe_print(text):
    """Remove emojis para evitar erros de encoding no Windows."""
    # Remove emojis e caracteres não-ASCII
    text_clean = re.sub(r'[^\x00-\x7F]+', ' ', str(text))
    print(text_clean)


def limpar_sessao(session_ids):
    db = SessionLocal()
    try:
        for sid in session_ids:
            db.query(ChatSessionState).filter(ChatSessionState.user_id == sid).delete()
        db.commit()
    finally:
        db.close()


print("\n" + "="*70)
print("TESTE 1: Validacao de contexto minimo")
print("="*70)

# Cimento com aplicacao + ambiente -> valido
context1 = {"product": "cimento", "application": "laje", "environment": "externa"}
result1 = _validate_minimum_context("cimento", context1)
print(f"1. Cimento (laje + externa): {result1} (esperado: True)")

# Cimento com apenas aplicacao "laje" (sem ambiente) -> invalido
context2 = {"product": "cimento", "application": "laje"}
result2 = _validate_minimum_context("cimento", context2)
print(f"2. Cimento (laje sem ambiente): {result2} (esperado: False)")

# Cimento sem aplicacao -> invalido
context3 = {"product": "cimento"}
result3 = _validate_minimum_context("cimento", context3)
print(f"3. Cimento (sem aplicacao): {result3} (esperado: False)")


print("\n" + "="*70)
print("TESTE 2: 'quero cimento' nao deve inferir contexto")
print("="*70)

session_id = "test_simple"
limpar_sessao([session_id])

reply, _ = handle_message("quero cimento", session_id)
safe_print(f"\n[Usuario] quero cimento")
safe_print(f"[Bot] {reply}\n")

# Verifica se pediu uso
if "uso" in reply.lower() or "qual" in reply.lower():
    print("OK: Bot perguntou sobre uso")
else:
    print("ERRO: Bot nao perguntou sobre uso!")

# Verifica se nao tem termos tecnicos
forbidden = ["reboco externo", "exposto", "area residencial", "cp iii", "cp iv"]
has_forbidden = any(term in reply.lower() for term in forbidden)

if not has_forbidden:
    print("OK: Bot nao inferiu contexto tecnico")
else:
    print("ERRO: Bot inferiu contexto tecnico prematuramente!")


print("\n" + "="*70)
print("TESTE 3: Fluxo progressivo completo")
print("="*70)

session_id2 = "test_progressive"
limpar_sessao([session_id2])

safe_print("\n[Usuario] quero cimento")
r1, _ = handle_message("quero cimento", session_id2)
safe_print(f"[Bot] {r1[:100]}...")

safe_print("\n[Usuario] pra laje")
r2, _ = handle_message("pra laje", session_id2)
safe_print(f"[Bot] {r2[:100]}...")

safe_print("\n[Usuario] externa")
r3, _ = handle_message("externa", session_id2)
safe_print(f"[Bot] {r3[:100]}...")

safe_print("\n[Usuario] exposta")
r4, _ = handle_message("exposta", session_id2)
safe_print(f"[Bot] {r4[:100]}...")

safe_print("\n[Usuario] residencial")
r5, _ = handle_message("residencial", session_id2)
safe_print(f"[Bot] {r5[:200]}...")

# Verifica estado final
st = get_state(session_id2)
print(f"\nEstado final:")
print(f"  application: {st.get('consultive_application')}")
print(f"  environment: {st.get('consultive_environment')}")
print(f"  exposure: {st.get('consultive_exposure')}")
print(f"  load_type: {st.get('consultive_load_type')}")

if st.get('consultive_application') == 'laje' and st.get('consultive_environment') in ['externa', 'externo']:
    print("\nOK: Estado coletado corretamente!")
else:
    print("\nERRO: Estado incorreto!")


print("\n" + "="*70)
print("TESTE 4: '50kg de cimento' nao deve bypasear")
print("="*70)

session_id3 = "test_50kg"
limpar_sessao([session_id3])

safe_print("\n[Usuario] quero 50kg de cimento")
r_50kg, _ = handle_message("quero 50kg de cimento", session_id3)
safe_print(f"[Bot] {r_50kg}")

if "uso" in r_50kg.lower() or "qual" in r_50kg.lower():
    print("\nOK: Bot perguntou sobre uso (mesmo com quantidade)")
else:
    print("\nERRO: Bot nao perguntou sobre uso!")

if "1)" not in r_50kg and "2)" not in r_50kg:
    print("OK: Bot nao mostrou catalogo direto")
else:
    print("ERRO: Bot mostrou catalogo sem investigar!")

print("\n" + "="*70)
print("TESTES CONCLUIDOS")
print("="*70)
