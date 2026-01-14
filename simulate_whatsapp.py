import requests

url = "http://localhost:8000/webhook/whatsapp"

payload = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA_TEST",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messages": [
                            {
                                "from": "5583996353706",
                                "id": "wamid.TEST123",
                                "timestamp": "1710000000",
                                "type": "text",
                                "text": {
                                    "body": "oi"
                                }
                            }
                        ]
                    }
                }
            ]
        }
    ]
}

resp = requests.post(url, json=payload)
print(resp.status_code)
print(resp.text)
