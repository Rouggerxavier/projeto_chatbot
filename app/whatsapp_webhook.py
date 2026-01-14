"""
Webhook endpoint for WhatsApp Business API (Meta).

Handles:
1. GET: Webhook verification from Meta
2. POST: Incoming WhatsApp messages
"""

import os
import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
# Define your Verify Token here (must match the token configured in Meta Dashboard)
# In production, load from environment variable
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "meuTokenSecreto123")

router = APIRouter(prefix="/webhook", tags=["whatsapp"])


# -----------------------------------------------------------------------------
# WEBHOOK VERIFICATION (GET)
# -----------------------------------------------------------------------------
@router.get("/whatsapp")
async def verify_webhook(request: Request):
    """
    Meta WhatsApp webhook verification endpoint.

    When you register the webhook in Meta Business Dashboard:
    - Meta sends GET request with hub.mode, hub.verify_token, hub.challenge
    - If mode="subscribe" AND token matches VERIFY_TOKEN:
      → Return hub.challenge as plain text (status 200)
    - Otherwise:
      → Return 403 Forbidden

    Reference: https://developers.facebook.com/docs/graph-api/webhooks/getting-started
    """
    # Extract query params manually (hub.mode, hub.verify_token, hub.challenge)
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info(f"Webhook verification: mode={mode}, token={token}, challenge={challenge}, VERIFY_TOKEN={VERIFY_TOKEN}")

    # Validate parameters
    if not all([mode, token, challenge]):
        logger.warning("Missing required parameters for webhook verification")
        raise HTTPException(status_code=400, detail="Missing parameters")

    # Verify mode and token
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        # CRITICAL: Return challenge as plain text, not JSON
        return Response(content=challenge, media_type="text/plain")

    # Invalid token or mode
    logger.warning(f"Webhook verification failed: mode={mode}, token={token}, expected={VERIFY_TOKEN}")
    raise HTTPException(status_code=403, detail="Forbidden")


# -----------------------------------------------------------------------------
# MESSAGE RECEIVER (POST)
# -----------------------------------------------------------------------------
class WhatsAppWebhookPayload(BaseModel):
    """
    WhatsApp webhook payload structure (simplified).

    Full schema: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
    """
    object: str
    entry: list[Dict[str, Any]]


@router.post("/whatsapp")
async def receive_whatsapp_message(request: Request):
    """
    Receives incoming WhatsApp messages from Meta.

    Flow:
    1. Meta sends POST with message data
    2. Extract message details (sender, text, type)
    3. Process message (integrate with flow_controller.py)
    4. Return 200 OK immediately (Meta requires fast response)

    TODO: Integrate with app/flow_controller.py to process messages
    TODO: Send replies via WhatsApp Business API
    """
    # CRITICAL: Accept raw JSON to prevent Pydantic validation failures
    # Meta payloads have optional/variable fields that break rigid schemas
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        # Still return 200 to prevent Meta retries
        return {"status": "error", "message": "invalid_json"}

    logger.info(f"Received WhatsApp webhook payload: {payload}")

    try:
        # Validate webhook object type
        webhook_object = payload.get("object")
        if webhook_object != "whatsapp_business_account":
            logger.warning(f"Unknown webhook object type: {webhook_object}")
            return {"status": "ignored"}

        # Process each entry (can contain multiple messages)
        for entry in payload.get("entry", []):
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})

                # Extract message data
                messages = value.get("messages", [])
                for message in messages:
                    msg_from = message.get("from")  # Sender phone number
                    msg_id = message.get("id")
                    msg_type = message.get("type")  # text, image, audio, etc.

                    # Handle text messages
                    if msg_type == "text":
                        text_body = message.get("text", {}).get("body", "")
                        logger.info(f"📩 Mensagem recebida de {msg_from}: {text_body}")

                        # Integrate with existing chatbot
                        from app.flow_controller import handle_message

                        try:
                            # Route message through chatbot flow
                            response, needs_human = handle_message(
                                message=text_body,
                                session_id=msg_from  # Use phone as session ID
                            )

                            logger.info(f"🤖 Resposta do chatbot: {response[:100]}...")

                            # Send reply back to WhatsApp
                            send_result = send_whatsapp_reply(msg_from, response)
                            logger.info(f"📤 Mensagem enviada com sucesso: {send_result.get('messages', [{}])[0].get('id', 'N/A')}")

                            if needs_human:
                                logger.warning(f"⚠️ Mensagem requer intervenção humana (session: {msg_from})")

                        except Exception as msg_error:
                            logger.error(f"❌ Erro ao processar mensagem de {msg_from}: {msg_error}", exc_info=True)
                            # Send fallback error message to user
                            try:
                                send_whatsapp_reply(
                                    msg_from,
                                    "Desculpe, ocorreu um erro. Por favor, tente novamente ou entre em contato conosco."
                                )
                            except Exception as send_error:
                                logger.error(f"❌ Falha ao enviar mensagem de erro: {send_error}")

                    else:
                        logger.info(f"📎 Tipo de mensagem não-texto ignorado: {msg_type} (de {msg_from})")

        # CRITICAL: Always return 200 OK quickly (within 20 seconds)
        # Meta will retry if no response or error status
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}", exc_info=True)
        # Still return 200 to prevent retries for malformed data
        return {"status": "error", "message": str(e)}


# -----------------------------------------------------------------------------
# HELPER: Send WhatsApp message
# -----------------------------------------------------------------------------
def send_whatsapp_reply(to: str, message: str) -> dict:
    """
    Send text message via WhatsApp Business API (Graph API).
    """
    import requests

    # Load credentials from environment (strip whitespace!)
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()

    if not phone_number_id or not access_token:
        error_msg = "Missing WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN in .env"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Sanitize recipient number (remove +, spaces, dashes)
    to_clean = to.replace("+", "").replace(" ", "").replace("-", "").strip()

    # Truncate message if too long (WhatsApp limit: 4096 chars)
    if len(message) > 4096:
        message = message[:4090] + "..."
        logger.warning(f"Message truncated to 4096 chars")

    # Graph API endpoint (use v18.0 for better compatibility)
    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_clean,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message
        }
    }

    # Log full request details for debug
    logger.info(f"📤 ENVIANDO WHATSAPP:")
    logger.info(f"   URL: {url}")
    logger.info(f"   TO: {to_clean}")
    logger.info(f"   MSG: {message[:100]}...")
    logger.info(f"   TOKEN (últimos 10): ...{access_token[-10:]}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        # Log raw response for debug
        logger.info(f"📥 RESPOSTA DA API:")
        logger.info(f"   Status: {response.status_code}")
        logger.info(f"   Body: {response.text}")

        # Check for errors
        if response.status_code >= 400:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("error", {}).get("message", response.text)
            error_code = error_data.get("error", {}).get("code", "N/A")
            logger.error(f"❌ WhatsApp API Error [{error_code}]: {error_msg}")
            raise Exception(f"WhatsApp API Error [{error_code}]: {error_msg}")

        result = response.json()

        # Verify message was accepted
        if "messages" in result and result["messages"]:
            msg_id = result["messages"][0].get("id", "N/A")
            logger.info(f"✅ Mensagem aceita pela API. ID: {msg_id}")
        else:
            logger.warning(f"⚠️ Resposta sem 'messages': {result}")

        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error: {e}")
        raise Exception(f"Network error: {e}")


# -----------------------------------------------------------------------------
# TESTING: Send test message
# -----------------------------------------------------------------------------
# Uncomment to test manually:
# if __name__ == "__main__":
#     from dotenv import load_dotenv
#     load_dotenv()
#     send_whatsapp_reply("5511999999999", "Teste de mensagem do chatbot!")
