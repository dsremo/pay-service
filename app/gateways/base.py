from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayOrder:
    order_ref: str
    raw: dict


@dataclass(frozen=True)
class GatewayRefund:
    refund_ref: str
    raw: dict


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    async def create_order(self, amount: int, currency: str, receipt: str) -> GatewayOrder:
        ...

    @abstractmethod
    async def refund(self, payment_ref: str, amount: int) -> GatewayRefund:
        ...
