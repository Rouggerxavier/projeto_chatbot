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
async def receive_whatsapp_message(payload: WhatsAppWebhookPayload):
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
    logger.info(f"Received WhatsApp webhook: {payload.object}")

    try:
        # Validate webhook object type
        if payload.object != "whatsapp_business_account":
            logger.warning(f"Unknown webhook object type: {payload.object}")
            return {"status": "ignored"}

        # Process each entry (can contain multiple messages)
        for entry in payload.entry:
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
                        logger.info(f"Message from {msg_from}: {text_body}")

                        # TODO: Integrate with existing chatbot
                        # Example:
                        # from app.flow_controller import handle_message
                        # response, needs_human = handle_message(
                        #     user_message=text_body,
                        #     session_id=msg_from,  # Use phone as session ID
                        #     db=...
                        # )
                        # await send_whatsapp_reply(msg_from, response)

                    else:
                        logger.info(f"Non-text message type: {msg_type}")

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

    Args:
        to: Recipient phone number in international format (e.g., "5511999999999")
        message: Text message to send (max 4096 chars)

    Returns:
        dict: API response with message ID if successful

    Raises:
        Exception: If request fails or env vars are missing

    Environment variables required:
    - WHATSAPP_PHONE_NUMBER_ID: Get from Meta Business Dashboard
      → App Dashboard → WhatsApp → API Setup → Phone Number ID
    - WHATSAPP_ACCESS_TOKEN: Permanent access token
      → App Dashboard → WhatsApp → API Setup → Permanent Token

    Reference:
    https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
    """
    import requests

    # Load credentials from environment
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    if not phone_number_id or not access_token:
        error_msg = "Missing WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN in .env"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Graph API endpoint
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"

    # Request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Message payload
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": message
        }
    }

    try:
        logger.info(f"Sending WhatsApp message to {to}: {message[:50]}...")

        # Send POST request
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()  # Raise exception for 4xx/5xx errors

        # Parse response
        result = response.json()
        logger.info(f"WhatsApp message sent successfully: {result}")
        return result

    except requests.exceptions.HTTPError as e:
        # API returned error (4xx/5xx)
        error_detail = e.response.json() if e.response else str(e)
        logger.error(f"WhatsApp API error: {error_detail}")
        raise Exception(f"Failed to send WhatsApp message: {error_detail}")

    except requests.exceptions.RequestException as e:
        # Network error, timeout, etc.
        logger.error(f"Network error sending WhatsApp message: {e}")
        raise Exception(f"Network error: {e}")


# -----------------------------------------------------------------------------
# TESTING: Send test message
# -----------------------------------------------------------------------------
# Uncomment to test manually:
# if __name__ == "__main__":
#     from dotenv import load_dotenv
#     load_dotenv()
#     send_whatsapp_reply("5511999999999", "Teste de mensagem do chatbot!")
