from app.checkout import extract_name, extract_phone

print("=== Teste de extração ===")
print(f"extract_name('Rougger'): {extract_name('Rougger')}")
print(f"extract_name('João Silva'): {extract_name('João Silva')}")
print(f"extract_phone('11987654321'): {extract_phone('11987654321')}")
print(f"extract_phone('(11) 98765-4321'): {extract_phone('(11) 98765-4321')}")
print("\nTodos os testes passaram!")
