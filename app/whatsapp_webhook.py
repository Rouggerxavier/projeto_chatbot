"""
Webhook endpoint for WhatsApp Business API (Meta).

Handles:
1. GET: Webhook verification from Meta
2. POST: Incoming WhatsApp messages
"""

import os
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request, Response, HTTPException

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
      -> Return hub.challenge as plain text (status 200)
    - Otherwise:
      -> Return 403 Forbidden

    Reference: https://developers.facebook.com/docs/graph-api/webhooks/getting-started
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info(
        "Webhook verification: mode=%s, token=%s, challenge=%s, VERIFY_TOKEN=%s",
        mode,
        token,
        challenge,
        VERIFY_TOKEN,
    )

    if not all([mode, token, challenge]):
        logger.warning("Missing required parameters for webhook verification")
        raise HTTPException(status_code=400, detail="Missing parameters")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed: mode=%s, token=%s", mode, token)
    raise HTTPException(status_code=403, detail="Forbidden")


# -----------------------------------------------------------------------------
# MESSAGE RECEIVER (POST)
# -----------------------------------------------------------------------------
@router.post("/whatsapp")
async def receive_whatsapp_message(request: Request):
    """
    Receives incoming WhatsApp messages from Meta.

    Flow:
    1. Meta sends POST with message data
    2. Extract message details (sender, text, type)
    3. Process message (integrate with flow_controller.py)
    4. Return 200 OK immediately (Meta requires fast response)
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook JSON: %s", e)
        # Still return 200 to prevent Meta retries
        return {"status": "error", "message": "invalid_json"}

    logger.info("Received WhatsApp webhook payload: %s", payload)

    try:
        # Validate webhook object type
        webhook_object = payload.get("object")
        if webhook_object != "whatsapp_business_account":
            logger.warning("Unknown webhook object type: %s", webhook_object)
            return {"status": "ignored"}

        # Process each entry (can contain multiple messages)
        for entry in payload.get("entry", []):
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})

                messages = value.get("messages", []) or []
                for message in messages:
                    msg_from = message.get("from")  # Sender phone number
                    msg_type = message.get("type")  # text, image, audio, etc.

                    # Handle text messages
                    if msg_type == "text":
                        text_body = message.get("text", {}).get("body", "")
                        logger.info("Message received from %s: %s", msg_from, text_body)

                        from app.flow_controller import handle_message

                        try:
                            # Route message through chatbot flow
                            response, needs_human = handle_message(
                                message=text_body,
                                session_id=msg_from,  # Use phone as session ID
                            )

                            logger.info("Chatbot response (truncated): %s", response[:200])

                            # Send reply back to WhatsApp
                            send_result = send_whatsapp_reply(msg_from, response)
                            logger.info(
                                "WhatsApp message sent: %s",
                                send_result.get("messages", [{}])[0].get("id", "N/A"),
                            )

                            if needs_human:
                                logger.warning("Message requires human intervention (session: %s)", msg_from)

                        except Exception as msg_error:
                            logger.error(
                                "Error processing message from %s: %s",
                                msg_from,
                                msg_error,
                                exc_info=True,
                            )
                            # Send fallback error message to user
                            try:
                                send_whatsapp_reply(
                                    msg_from,
                                    "Desculpe, ocorreu um erro. Por favor, tente novamente ou entre em contato conosco.",
                                )
                            except Exception as send_error:
                                logger.error("Failed to send error message: %s", send_error)

                    else:
                        logger.info("Non-text message ignored: %s (from %s)", msg_type, msg_from)

        # Always return 200 OK quickly (within 20 seconds).
        # Meta will retry if no response or error status.
        return {"status": "ok"}

    except Exception as e:
        logger.error("Error processing WhatsApp webhook: %s", e, exc_info=True)
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
        logger.warning("Message truncated to 4096 chars")

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
            "body": message,
        },
    }

    logger.info("Sending WhatsApp message")
    logger.info("   URL: %s", url)
    logger.info("   TO: %s", to_clean)
    logger.info("   MSG: %s...", message[:100])
    logger.info("   TOKEN (last 10): ...%s", access_token[-10:])

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        logger.info("WhatsApp API response:")
        logger.info("   Status: %s", response.status_code)
        logger.info("   Body: %s", response.text)

        if response.status_code >= 400:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("error", {}).get("message", response.text)
            error_code = error_data.get("error", {}).get("code", "N/A")
            logger.error("WhatsApp API Error [%s]: %s", error_code, error_msg)
            raise Exception(f"WhatsApp API Error [{error_code}]: {error_msg}")

        result = response.json()

        if "messages" in result and result["messages"]:
            msg_id = result["messages"][0].get("id", "N/A")
            logger.info("Message accepted by the API. ID: %s", msg_id)
        else:
            logger.warning("Response without 'messages': %s", result)

        return result

    except requests.exceptions.RequestException as e:
        logger.error("Network error: %s", e)
        raise Exception(f"Network error: {e}")


# -----------------------------------------------------------------------------
# TESTING: Send test message
# -----------------------------------------------------------------------------
# Uncomment to test manually:
# if __name__ == "__main__":
#     from dotenv import load_dotenv
#     load_dotenv()
#     send_whatsapp_reply("5511999999999", "Teste de mensagem do chatbot!")
