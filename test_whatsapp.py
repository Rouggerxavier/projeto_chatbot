"""
Test script for WhatsApp message sending.

Usage:
1. Update the phone number below (international format: 5511999999999)
2. Run: python test_whatsapp.py
"""

from dotenv import load_dotenv
load_dotenv()

from app.whatsapp_webhook import send_whatsapp_reply

# TODO: Replace with your test phone number (international format)
# Example: "5511999999999" for Brazil +55 11 99999-9999
TEST_PHONE = "5583996353706"

# Test message
TEST_MESSAGE = "Teste de mensagem do chatbot! 🚀"

if __name__ == "__main__":
    try:
        print(f"Sending test message to {TEST_PHONE}...")
        result = send_whatsapp_reply(TEST_PHONE, TEST_MESSAGE)
        print(f"✅ Message sent successfully!")
        print(f"Response: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")
