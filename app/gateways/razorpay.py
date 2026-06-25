import base64

import httpx

from app.config import settings
from app.gateways.base import GatewayOrder, GatewayRefund, PaymentGateway

_API_BASE = "https://api.razorpay.com/v1"


class RazorpayGateway(PaymentGateway):
    name = "razorpay"

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()
        ).decode()
        return f"Basic {token}"

    async def create_order(self, amount: int, currency: str, receipt: str) -> GatewayOrder:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_API_BASE}/orders",
                headers={"Authorization": self._auth_header()},
                json={"amount": amount, "currency": currency, "receipt": receipt, "payment_capture": 1},
            )
            response.raise_for_status()
            payload = response.json()
        return GatewayOrder(order_ref=payload["id"], raw=payload)

    async def refund(self, payment_ref: str, amount: int) -> GatewayRefund:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_API_BASE}/payments/{payment_ref}/refund",
                headers={"Authorization": self._auth_header()},
                json={"amount": amount},
            )
            response.raise_for_status()
            payload = response.json()
        return GatewayRefund(refund_ref=payload["id"], raw=payload)
