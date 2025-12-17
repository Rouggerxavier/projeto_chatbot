import os
from typing import Any, Dict, Optional

import requests

MP_API_BASE = "https://api.mercadopago.com"


def _get_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return v


def _auth_headers() -> Dict[str, str]:
    token = _get_env("MP_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {token}"}


def create_checkout_preference(
    pedido_id: int,
    total: float,
    title: Optional[str] = None,
    notification_url: Optional[str] = None,
    payer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cria uma *Preference* (Checkout Pro) e retorna o link de pagamento.

    Observação:
    - O Checkout Pro permite que o cliente escolha Pix ou cartão dentro do checkout,
      então dá pra começar sem montar payload específico por método.
    """
    if total is None or float(total) <= 0:
        raise ValueError("total inválido para criar pagamento")

    payload: Dict[str, Any] = {
        "items": [
            {
                "title": title or f"Pedido #{pedido_id} (materiais de construção)",
                "quantity": 1,
                "unit_price": float(total),
            }
        ],
        "external_reference": f"pedido:{pedido_id}",
    }

    if notification_url:
        payload["notification_url"] = notification_url

    if payer_email:
        payload["payer"] = {"email": payer_email}

    r = requests.post(
        f"{MP_API_BASE}/checkout/preferences",
        headers=_auth_headers(),
        json=payload,
        timeout=30,
    )
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
