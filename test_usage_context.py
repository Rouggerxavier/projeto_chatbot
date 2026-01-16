# -*- coding: utf-8 -*-
"""
Testa o modo de esclarecimento de uso (contexto pré-venda).

Execute: python test_usage_context.py
"""
import sys
import io

# Fix encoding para Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.flows.usage_context import is_generic_product
from app.parsing import extract_product_hint

# Casos de teste
test_cases = [
    # GENÉRICOS (devem perguntar contexto)
    ("quero cimento", True, "cimento"),
    ("preciso de tinta", True, "tinta"),
    ("areia", True, "areia"),
    ("brita", True, "brita"),
    ("argamassa", True, "argamassa"),

    # ESPECÍFICOS (devem mostrar catálogo direto)
    ("quero cimento cp ii", False, "cimento cp ii"),
    ("cimento cp ii 50kg", False, "cimento cp ii"),  # parsing remove "50kg"
    ("tinta latex branca", False, "tinta latex branca"),
    ("areia fina", False, "areia fina"),
    ("areia media", False, "areia media"),
    ("brita 1", True, "brita"),  # parsing remove "1", então fica genérico
    ("argamassa colante", False, "argamassa colante"),

    # COM QUANTIDADE (vai direto pro catálogo, mesmo genérico)
    ("2 sacos de cimento", True, "cimento"),  # hint é genérico, mas tem quantidade
    ("3m3 de areia", True, "areia"),

    # NÃO-PRODUTOS (não devem acionar)
    ("quero trena", False, "trena"),
    ("preciso de martelo", False, "martelo"),
]

print("=" * 80)
print("TESTE: MODO DE ESCLARECIMENTO DE USO (CONTEXTO PRE-VENDA)")
print("=" * 80)

passed = 0
failed = 0

for msg, expected_generic, expected_hint in test_cases:
    hint = extract_product_hint(msg)
    result_generic = is_generic_product(hint)

    # Verifica se bateu com o esperado
    hint_ok = hint == expected_hint
    generic_ok = result_generic == expected_generic

    if hint_ok and generic_ok:
        status = "[OK] PASS"
        passed += 1
    else:
        status = "[X] FAIL"
        failed += 1

    print(f"\n{status}")
    print(f"  MSG: \"{msg}\"")
    print(f"  Hint extraido: \"{hint}\" (esperado: \"{expected_hint}\")")
    print(f"  E generico: {result_generic} (esperado: {expected_generic})")

print("\n" + "=" * 80)
print(f"RESULTADO: {passed} passou, {failed} falhou")
print("=" * 80)

if failed == 0:
    print("[OK] Todos os testes passaram!")
else:
    print(f"[!] {failed} teste(s) falharam. Ajuste os padroes.")
