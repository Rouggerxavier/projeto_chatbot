import os
import uuid
from typing import Any, Dict, Optional

import requests

MP_API_BASE = "https://api.mercadopago.com"


def _get_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return v


def _get_env_optional(name: str) -> Optional[str]:
    v = os.environ.get(name)
    if not v:
        return None
    return v


def _auth_headers() -> Dict[str, str]:
    token = _get_env("MP_ACCESS_TOKEN").strip().strip('"').strip("'")
    if not token or len(token) < 20:
        raise RuntimeError(f"MP_ACCESS_TOKEN inválido (comprimento={len(token)})")
    print(f"🔑 Token MP (primeiros 20 chars): {token[:20]}...")
    return {"Authorization": f"Bearer {token}"}


def _default_back_urls() -> Optional[Dict[str, str]]:
    urls = {
        "success": _get_env_optional("MP_SUCCESS_URL"),
        "pending": _get_env_optional("MP_PENDING_URL"),
        "failure": _get_env_optional("MP_FAILURE_URL"),
    }
    cleaned = {k: v for k, v in urls.items() if v}
    if not cleaned:
        return None
    return cleaned


def create_checkout_preference(
    pedido_id: int,
    total: float,
    title: Optional[str] = None,
    notification_url: Optional[str] = None,
    payer_email: Optional[str] = None,
    back_urls: Optional[Dict[str, str]] = None,
    auto_return: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Cria uma *Preference* (Checkout Pro) e retorna o link de pagamento.

    Observação:
    - O Checkout Pro permite que o cliente escolha Pix ou cartão dentro do checkout,
      então dá pra começar sem montar payload específico por método.
    """
    if total is None or float(total) <= 0:
        raise ValueError("total inválido para criar pagamento")

    resolved_notification = notification_url or _get_env_optional("MP_NOTIFICATION_URL")
    resolved_back_urls = back_urls or _default_back_urls()
    resolved_auto_return = auto_return or _get_env_optional("MP_AUTO_RETURN")
    resolved_payer_email = payer_email or _get_env_optional("MP_DEFAULT_PAYER_EMAIL")

    payload: Dict[str, Any] = {
        "items": [
            {
                "title": title or f"Pedido #{pedido_id} (materiais de construção)",
                "quantity": 1,
                "unit_price": float(total),
            }
        ],
        "external_reference": f"pedido:{pedido_id}",
        "metadata": metadata or {"pedido_id": pedido_id},
    }
    
    # Só adiciona auto_return se houver back_urls
    if resolved_back_urls and resolved_auto_return:
        payload["auto_return"] = resolved_auto_return

    if resolved_notification:
        payload["notification_url"] = resolved_notification

    if resolved_back_urls:
        payload["back_urls"] = resolved_back_urls

    if resolved_payer_email:
        payload["payer"] = {"email": resolved_payer_email}

    print(f"📤 Enviando payload para MP Preference: {payload}")
    
    r = requests.post(
        f"{MP_API_BASE}/checkout/preferences",
        headers=_auth_headers(),
        json=payload,
        timeout=30,
    )
    
    if r.status_code != 200 and r.status_code != 201:
        print(f"❌ Resposta MP (status={r.status_code}): {r.text[:1000]}")
    
    r.raise_for_status()
    data = r.json()

    return {
        "preference_id": data.get("id"),
        "init_point": data.get("init_point"),
        "sandbox_init_point": data.get("sandbox_init_point"),
    }


def choose_best_payment_link(pref: Dict[str, Any]) -> Optional[str]:
    # Em teste normalmente vem o sandbox_init_point.
    return pref.get("sandbox_init_point") or pref.get("init_point")


def create_pix_payment(
    pedido_id: int,
    total: float,
    description: Optional[str] = None,
    notification_url: Optional[str] = None,
    payer_email: Optional[str] = None,
    payer_first_name: Optional[str] = None,
    payer_last_name: Optional[str] = None,
    payer_identification: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if total is None or float(total) <= 0:
        raise ValueError("total inválido para criar pagamento PIX")

    resolved_notification = notification_url or _get_env_optional("MP_NOTIFICATION_URL")
    resolved_email = payer_email or _get_env_optional("MP_DEFAULT_PAYER_EMAIL") or f"cliente+{pedido_id}@example.com"

    payer: Dict[str, Any] = {"email": resolved_email}
    if payer_first_name:
        payer["first_name"] = payer_first_name
    if payer_last_name:
        payer["last_name"] = payer_last_name
    if payer_identification:
        payer["identification"] = payer_identification

    payload: Dict[str, Any] = {
        "transaction_amount": float(total),
        "description": description or f"Pedido #{pedido_id} (PIX)",
        "payment_method_id": "pix",
        "external_reference": f"pedido:{pedido_id}",
        "metadata": metadata or {"pedido_id": pedido_id},
        "payer": payer,
    }

    if resolved_notification:
        payload["notification_url"] = resolved_notification

    print(f"📤 Enviando payload para MP: {payload}")
    
    headers = _auth_headers()
    headers["X-Idempotency-Key"] = str(uuid.uuid4())
    
    r = requests.post(
        f"{MP_API_BASE}/v1/payments",
        headers=headers,
        json=payload,
        timeout=30,
    )
    
    if r.status_code != 200 and r.status_code != 201:
        print(f"❌ Resposta MP (status={r.status_code}): {r.text[:500]}")
    
    r.raise_for_status()
    data = r.json()

    transaction_data = data.get("point_of_interaction", {}).get("transaction_data", {})

    return {
        "payment_id": data.get("id"),
        "status": data.get("status"),
        "status_detail": data.get("status_detail"),
        "qr_code": transaction_data.get("qr_code"),
        "qr_code_base64": transaction_data.get("qr_code_base64"),
        "ticket_url": transaction_data.get("ticket_url"),
        "expiration": transaction_data.get("expiration_date"),
        "copy_and_paste": transaction_data.get("qr_code"),
    }
