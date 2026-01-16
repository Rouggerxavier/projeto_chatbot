"""
Testa o modo consultivo vs modo venda.

Execute: python test_consultive.py
"""
from app.text_utils import is_consultive_question, has_product_intent

# Casos de teste
test_cases = [
    # CONSULTIVAS (devem retornar True)
    ("Esse cimento serve pra laje?", True, False),
    ("Posso usar isso em área externa?", True, False),
    ("Qual é melhor pra banheiro?", True, False),
    ("Areia serve pra reboco?", True, False),
    ("Como usar massa corrida?", True, False),
    ("Esse produto é resistente?", True, False),
    ("É bom pra obra?", True, False),

    # VENDAS (devem retornar False para consultiva, True para product_intent)
    ("Quero 2 sacos de cimento", False, True),
    ("Adiciona areia no carrinho", False, True),
    ("Preciso de tinta", False, True),
    ("Me dá 3 kg de prego", False, True),
    ("Quero comprar tijolo", False, True),

    # AÇÕES (devem retornar False para ambos)
    ("Mostra o carrinho", False, False),
    ("Finalizar pedido", False, False),
    ("Meu CEP é 58000-000", False, False),
    ("Entrega ou retirada?", False, False),

    # SAUDAÇÕES (False para ambos)
    ("Oi", False, False),
    ("Bom dia", False, False),
]

print("=" * 80)
print("TESTE: MODO CONSULTIVO vs MODO VENDA")
print("=" * 80)

passed = 0
failed = 0

for msg, expected_consultive, expected_product in test_cases:
    result_consultive = is_consultive_question(msg)
    result_product = has_product_intent(msg)

    # Verifica se bateu com o esperado
    consultive_ok = result_consultive == expected_consultive
    product_ok = result_product == expected_product

    if consultive_ok and product_ok:
        status = "✅ PASS"
        passed += 1
    else:
        status = "❌ FAIL"
        failed += 1

    print(f"\n{status}")
    print(f"  MSG: \"{msg}\"")
    print(f"  Consultiva: {result_consultive} (esperado: {expected_consultive})")
    print(f"  Produto:    {result_product} (esperado: {expected_product})")

print("\n" + "=" * 80)
print(f"RESULTADO: {passed} passou, {failed} falhou")
print("=" * 80)

if failed == 0:
    print("✅ Todos os testes passaram!")
else:
    print(f"⚠️ {failed} teste(s) falharam. Ajuste os padrões.")
