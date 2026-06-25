import uuid

from app.gateways.base import GatewayOrder, GatewayRefund, PaymentGateway


class MockGateway(PaymentGateway):
    name = "mock"

    async def create_order(self, amount: int, currency: str, receipt: str) -> GatewayOrder:
        order_ref = "mockord_" + uuid.uuid4().hex
        return GatewayOrder(order_ref=order_ref, raw={"amount": amount, "currency": currency, "receipt": receipt})

    async def refund(self, payment_ref: str, amount: int) -> GatewayRefund:
        refund_ref = "mockrfnd_" + uuid.uuid4().hex
        return GatewayRefund(refund_ref=refund_ref, raw={"amount": amount, "payment_ref": payment_ref})
