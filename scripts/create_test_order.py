"""Utility to create and capture a sandbox order for dispute simulation."""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api-m.sandbox.paypal.com"


def get_token() -> str:
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    resp = requests.post(
        f"{BASE_URL}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_order(amount: str = "25.00", description: str = "Mechanical Keyboard") -> dict:
    token = get_token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": "USD",
                "value": amount,
                "breakdown": {
                    "item_total": {"currency_code": "USD", "value": amount}
                }
            },
            "items": [{
                "name": description,
                "quantity": "1",
                "unit_amount": {"currency_code": "USD", "value": amount},
                "category": "PHYSICAL_GOODS"
            }]
        }],
        "application_context": {
            "return_url": "https://example.com/return",
            "cancel_url": "https://example.com/cancel",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW"
        }
    }
    resp = requests.post(
        f"{BASE_URL}/v2/checkout/orders",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def capture_order(order_id: str) -> dict:
    token = get_token()
    resp = requests.post(
        f"{BASE_URL}/v2/checkout/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        oid = sys.argv[2]
        res = capture_order(oid)
        print("Captured:", res.get("status"), res.get("id"))
    else:
        order = create_order()
        oid = order["id"]
        approve_link = next(l["href"] for l in order["links"] if l["rel"] == "approve")
        print(f"ORDER_ID={oid}")
        print(f"APPROVE_URL={approve_link}")
