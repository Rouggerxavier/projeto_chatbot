import os
import re
from typing import Any, Dict, Optional

import requests

MP_API_BASE = "https://api.mercadopago.com"
MP_REQUEST_TIMEOUT = int(os.environ.get("REQUESTS_TIMEOUT", "60"))


def _validate_email(email: Optional[str]) -> str:
    """Valida e retorna email, ou lanca excecao se invalido."""
    if not email:
        raise ValueError("Email e obrigatorio para pagamento online")

    email = email.strip()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email):
        raise ValueError(f"Email invalido: {email}")

    # Rejeita emails de teste/exemplo
    if email.endswith(("@example.com", "@test.com", "@localhost")):
        raise ValueError(f"Email de teste nao permitido: {email}")

    return email


def _get_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return v


def _get_env_optional(name: str) -> Optional[str]:
    v = os.environ.get(name)
    if not v:
        return None
    return v


def _auth_headers() -> Dict[str, str]:
    token = _get_env("MP_ACCESS_TOKEN").strip().strip('"').strip("'")
    if not token or len(token) < 20:
        raise RuntimeError(f"MP_ACCESS_TOKEN invalido (comprimento={len(token)})")
    print("[MP] Token carregado (redigido)")
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

    Observacao:
    - O Checkout Pro permite que o cliente escolha Pix ou cartao dentro do checkout,
      entao nao precisa payload especifico por metodo.
    """
    if total is None or float(total) <= 0:
        raise ValueError("total invalido para criar pagamento")

    resolved_notification = notification_url or _get_env_optional("MP_NOTIFICATION_URL")
    resolved_back_urls = back_urls or _default_back_urls()
    resolved_auto_return = auto_return or _get_env_optional("MP_AUTO_RETURN")
    resolved_payer_email = payer_email or _get_env_optional("MP_DEFAULT_PAYER_EMAIL")

    payload: Dict[str, Any] = {
        "items": [
            {
                "title": title or f"Pedido #{pedido_id} (materiais de construcao)",
                "quantity": 1,
                "unit_price": float(total),
            }
        ],
        "external_reference": f"pedido:{pedido_id}",
        "metadata": metadata or {"pedido_id": pedido_id},
    }

    # So adiciona auto_return se houver back_urls
    if resolved_back_urls and resolved_auto_return:
        payload["auto_return"] = resolved_auto_return

    if resolved_notification:
        payload["notification_url"] = resolved_notification

    if resolved_back_urls:
        payload["back_urls"] = resolved_back_urls

    if resolved_payer_email:
        try:
            validated_email = _validate_email(resolved_payer_email)
            payload["payer"] = {"email": validated_email}
        except ValueError as e:
            print(f"[MP] Email invalido no preference: {e}")

    print(f"[MP] Enviando payload para Preference: {payload}")

    r = requests.post(
        f"{MP_API_BASE}/checkout/preferences",
        headers=_auth_headers(),
        json=payload,
        timeout=MP_REQUEST_TIMEOUT,
    )

    if r.status_code not in (200, 201):
        print(f"[MP] Resposta MP (status={r.status_code}): {r.text[:1000]}")

    r.raise_for_status()
    data = r.json()

    return {
        "preference_id": data.get("id"),
        "init_point": data.get("init_point"),
        "sandbox_init_point": data.get("sandbox_init_point"),
    }
