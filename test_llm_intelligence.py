"""
Teste das novas capacidades de inteligência usando LLM.

Testa:
1. Interpretação semântica de escolha
2. Síntese técnica contextual
"""
import os
from dotenv import load_dotenv

# Carrega .env
load_dotenv()

from app.llm_service import interpret_choice, generate_technical_synthesis, extract_product_factors


def test_interpret_choice():
    """Testa interpretação de escolhas naturais."""
    print("\n=== TESTE 1: INTERPRETAÇÃO SEMÂNTICA DE ESCOLHA ===")

    options = [
        {"id": 101, "nome": "Cimento CP II 50kg"},
        {"id": 102, "nome": "Cimento CP III 50kg"},
        {"id": 103, "nome": "Cimento CP IV 50kg"},
    ]

    # Casos de teste
    test_cases = [
        ("2", 2, "Número direto"),
        ("sim, a 2", 2, "Confirmação + número"),
        ("essa segunda", 2, "Demonstrativo + posição"),
        ("quero o primeiro", 1, "Verbo + posição"),
        ("pode ser a 3", 3, "Expressão + número"),
        ("a primeira opção", 1, "Posição com palavra extra"),
        ("vou levar essa terceira", 3, "Expressão + demonstrativo + posição"),
    ]

    passed = 0
    failed = 0

    for message, expected, description in test_cases:
        result = interpret_choice(message, options)
        status = "[OK]" if result == expected else "[FAIL]"
        passed += 1 if result == expected else 0
        failed += 1 if result != expected else 0
        print(f"{status} {description:30} '{message:25}' -> {result} (esperado: {expected})")

    print(f"\n{passed} passou, {failed} falhou")
    return failed == 0


def test_technical_synthesis():
    """Testa geração de síntese técnica."""
    print("\n=== TESTE 2: SÍNTESE TÉCNICA CONTEXTUAL ===")

    # Caso 1: Cimento para laje externa exposta residencial
    context1 = {
        "product": "cimento",
        "application": "laje",
        "environment": "externa",
        "exposure": "exposto",
        "load_type": "residencial",
    }

    factors1 = extract_product_factors("cimento")
    print(f"\nCaso 1: {context1}")
    print(f"Fatores técnicos: {', '.join(factors1)}")

    synthesis1 = generate_technical_synthesis("cimento", context1, factors1)
    print(f"Síntese gerada:\n{synthesis1}")

    # Validações
    checks1 = [
        ("Menciona 'laje'", "laje" in synthesis1.lower()),
        ("Menciona 'externa'", "externa" in synthesis1.lower()),
        ("Menciona 'exposto' ou 'exposição'", "expos" in synthesis1.lower()),
        ("Menciona aspecto técnico", any(w in synthesis1.lower() for w in ["sulfato", "umidade", "durabilidade", "resistente"])),
        ("Tamanho razoável (> 50 chars)", len(synthesis1) > 50),
    ]

    passed1 = sum(1 for _, check in checks1 if check)
    for name, result in checks1:
        status = "[OK]" if result else "[FAIL]"
        print(f"{status} {name}")

    # Caso 2: Tinta para parede interna
    context2 = {
        "product": "tinta",
        "application": "parede",
        "surface": "parede",
        "environment": "interna",
    }

    factors2 = extract_product_factors("tinta")
    print(f"\nCaso 2: {context2}")
    print(f"Fatores técnicos: {', '.join(factors2)}")

    synthesis2 = generate_technical_synthesis("tinta", context2, factors2)
    print(f"Síntese gerada:\n{synthesis2}")

    checks2 = [
        ("Menciona 'parede' ou 'pintura'", any(w in synthesis2.lower() for w in ["parede", "pintura"])),
        ("Menciona 'interna' ou 'interno'", "intern" in synthesis2.lower()),
        ("Tamanho razoável (> 50 chars)", len(synthesis2) > 50),
    ]

    passed2 = sum(1 for _, check in checks2 if check)
    for name, result in checks2:
        status = "[OK]" if result else "[FAIL]"
        print(f"{status} {name}")

    total_passed = passed1 + passed2
    total_checks = len(checks1) + len(checks2)
    print(f"\n{total_passed}/{total_checks} verificações passaram")

    return total_passed == total_checks


if __name__ == "__main__":
    try:
        print("=" * 80)
        print("TESTE DE INTELIGÊNCIA LLM (GROQ)")
        print("=" * 80)

        test1_ok = test_interpret_choice()
        test2_ok = test_technical_synthesis()

        print("\n" + "=" * 80)
        if test1_ok and test2_ok:
            print("[OK] TODOS OS TESTES PASSARAM!")
        else:
            print("[FAIL] ALGUNS TESTES FALHARAM")
            if not test1_ok:
                print("  - Interpretacao de escolha: FALHOU")
            if not test2_ok:
                print("  - Sintese tecnica: FALHOU")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
