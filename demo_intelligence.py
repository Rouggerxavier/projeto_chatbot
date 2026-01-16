"""
Demonstração interativa das novas capacidades de inteligência LLM.

Execute: python demo_intelligence.py

Mostra:
1. Interpretação semântica de escolha
2. Síntese técnica contextual
"""
import os
from dotenv import load_dotenv

# Carrega .env
load_dotenv()

from app.llm_service import interpret_choice, generate_technical_synthesis, extract_product_factors


def demo_choice_interpretation():
    """Demo: Interpretação semântica de escolha."""
    print("\n" + "=" * 80)
    print("DEMO 1: INTERPRETACAO SEMANTICA DE ESCOLHA")
    print("=" * 80)

    # Simula catálogo exibido
    options = [
        {"id": 101, "nome": "Cimento CP II 50kg - R$ 35.90"},
        {"id": 102, "nome": "Cimento CP III 50kg - R$ 38.50"},
        {"id": 103, "nome": "Cimento CP IV 50kg - R$ 42.00"},
    ]

    print("\nCATALOGO EXIBIDO:")
    for idx, opt in enumerate(options, 1):
        print(f"  {idx}) {opt['nome']}")

    print("\n" + "-" * 80)
    print("TESTANDO DIFERENTES FORMAS DE ESCOLHA:")
    print("-" * 80)

    test_messages = [
        "2",
        "sim, a 2",
        "essa segunda",
        "quero o primeiro",
        "pode ser a 3",
        "vou levar o segundo",
        "a primeira opcao",
    ]

    for msg in test_messages:
        result = interpret_choice(msg, options)
        if result:
            escolhido = options[result - 1]["nome"]
            print(f"\nUsuario: '{msg}'")
            print(f"  -> Interpretado como: Opcao {result}")
            print(f"  -> Produto: {escolhido}")
        else:
            print(f"\nUsuario: '{msg}'")
            print(f"  -> Nao identificado")

    print("\n" + "=" * 80)


def demo_technical_synthesis():
    """Demo: Síntese técnica contextual."""
    print("\n" + "=" * 80)
    print("DEMO 2: SINTESE TECNICA CONTEXTUAL")
    print("=" * 80)

    # Caso 1: Cimento para laje
    print("\n" + "-" * 80)
    print("CASO 1: CIMENTO PARA LAJE EXTERNA EXPOSTA RESIDENCIAL")
    print("-" * 80)

    context1 = {
        "product": "cimento",
        "application": "laje",
        "environment": "externa",
        "exposure": "exposto",
        "load_type": "residencial",
    }

    print("\nCONTEXTO COLETADO:")
    print(f"  Produto: {context1['product']}")
    print(f"  Aplicacao: {context1['application']}")
    print(f"  Ambiente: {context1['environment']}")
    print(f"  Exposicao: {context1['exposure']}")
    print(f"  Tipo de carga: {context1['load_type']}")

    factors1 = extract_product_factors("cimento")
    print(f"\nFATORES TECNICOS RELEVANTES:")
    for f in factors1:
        print(f"  - {f}")

    print("\nSINTESE GERADA PELA LLM:")
    synthesis1 = generate_technical_synthesis("cimento", context1, factors1)
    print(f"\n{synthesis1}")

    # Caso 2: Tinta para parede interna
    print("\n" + "-" * 80)
    print("CASO 2: TINTA PARA PAREDE INTERNA")
    print("-" * 80)

    context2 = {
        "product": "tinta",
        "application": "parede",
        "surface": "parede",
        "environment": "interna",
    }

    print("\nCONTEXTO COLETADO:")
    print(f"  Produto: {context2['product']}")
    print(f"  Aplicacao: {context2['application']}")
    print(f"  Superficie: {context2['surface']}")
    print(f"  Ambiente: {context2['environment']}")

    factors2 = extract_product_factors("tinta")
    print(f"\nFATORES TECNICOS RELEVANTES:")
    for f in factors2:
        print(f"  - {f}")

    print("\nSINTESE GERADA PELA LLM:")
    synthesis2 = generate_technical_synthesis("tinta", context2, factors2)
    print(f"\n{synthesis2}")

    # Caso 3: Areia para reboco fino
    print("\n" + "-" * 80)
    print("CASO 3: AREIA PARA REBOCO FINO")
    print("-" * 80)

    context3 = {
        "product": "areia",
        "application": "reboco",
        "grain": "fino",
    }

    print("\nCONTEXTO COLETADO:")
    print(f"  Produto: {context3['product']}")
    print(f"  Aplicacao: {context3['application']}")
    print(f"  Granulometria: {context3['grain']}")

    factors3 = extract_product_factors("areia")
    print(f"\nFATORES TECNICOS RELEVANTES:")
    for f in factors3:
        print(f"  - {f}")

    print("\nSINTESE GERADA PELA LLM:")
    synthesis3 = generate_technical_synthesis("areia", context3, factors3)
    print(f"\n{synthesis3}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    print("=" * 80)
    print("DEMONSTRACAO: INTELIGENCIA LLM - CHATBOT CONSTRULAR")
    print("=" * 80)
    print("\nEste script demonstra as duas melhorias de inteligencia:")
    print("1. Interpretacao semantica de escolha (entende linguagem natural)")
    print("2. Sintese tecnica contextual (explica POR QUE recomendar)")

    try:
        demo_choice_interpretation()
        demo_technical_synthesis()

        print("\n" + "=" * 80)
        print("DEMONSTRACAO COMPLETA!")
        print("=" * 80)
        print("\nPROXIMO PASSO: Teste no Streamlit")
        print("  Execute: streamlit run streamlit_app.py")
        print("\n  Teste o fluxo completo:")
        print("  1. 'quero cimento'")
        print("  2. 'pra laje'")
        print("  3. 'externa'")
        print("  4. 'exposto'")
        print("  5. 'residencial'")
        print("  6. 'sim'")
        print("  7. 'essa segunda' (ou outra variacao natural)")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
