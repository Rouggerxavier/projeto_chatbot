"""
Teste MÍNIMO de envio WhatsApp - sem chatbot, sem webhook.
Execute: python test_whatsapp_send.py

Se isso funcionar e a mensagem chegar, o problema está no fluxo do webhook.
Se isso NÃO funcionar, o problema está nas credenciais ou configuração Meta.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_send():
    # Credenciais (strip para remover espaços)
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()

    print(f"📋 CONFIGURAÇÃO:")
    print(f"   Phone Number ID: {phone_number_id}")
    print(f"   Token (últimos 15): ...{access_token[-15:]}")

    # IMPORTANTE: Coloque seu número de teste aqui!
    # Formato: código do país + DDD + número (sem +, espaços ou traços)
    # Exemplo Brasil: 5583999999999
    NUMERO_DESTINO = input("Digite o número destino (ex: 5583999999999): ").strip()

    if not NUMERO_DESTINO:
        print("❌ Número não informado!")
        return

    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Payload mínimo
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": NUMERO_DESTINO,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": "Teste de envio direto - se você receber isso, a API funciona!"
        }
    }

    print(f"\n📤 ENVIANDO PARA: {NUMERO_DESTINO}")
    print(f"   URL: {url}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        print(f"\n📥 RESPOSTA:")
        print(f"   Status Code: {response.status_code}")
        print(f"   Body: {response.text}")

        if response.status_code == 200:
            data = response.json()
            if "messages" in data:
                print(f"\n✅ SUCESSO! Message ID: {data['messages'][0]['id']}")
                print("   Verifique se a mensagem chegou no WhatsApp.")
                print("\n   Se NÃO chegou, possíveis causas:")
                print("   1. Número não está na lista de teste (se app em Development)")
                print("   2. Janela de 24h expirou (usuário precisa enviar msg primeiro)")
                print("   3. Número bloqueou o remetente")
            else:
                print(f"\n⚠️ Resposta inesperada: {data}")
        else:
            print(f"\n❌ ERRO NA API!")
            try:
                error = response.json().get("error", {})
                print(f"   Code: {error.get('code')}")
                print(f"   Message: {error.get('message')}")
                print(f"   Type: {error.get('type')}")

                # Diagnóstico baseado no erro
                if error.get("code") == 190:
                    print("\n   💡 Token inválido ou expirado!")
                elif error.get("code") == 131030:
                    print("\n   💡 Número não verificado ou fora da janela de 24h!")
                elif error.get("code") == 131026:
                    print("\n   💡 Número não está na lista de teste!")
            except:
                pass

    except Exception as e:
        print(f"\n❌ ERRO DE REDE: {e}")

if __name__ == "__main__":
    test_send()
