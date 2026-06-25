from app.config import settings
from app.gateways.base import PaymentGateway
from app.gateways.mock import MockGateway
from app.gateways.razorpay import RazorpayGateway

_REGISTRY: dict[str, PaymentGateway] = {
    "mock": MockGateway(),
    "razorpay": RazorpayGateway(),
}


def default_gateway_name() -> str:
    return "razorpay" if settings.razorpay_enabled else "mock"


def get_gateway(name: str | None = None) -> PaymentGateway:
    resolved = name or default_gateway_name()
    gateway = _REGISTRY.get(resolved)
    if gateway is None:
        raise ValueError(f"unknown gateway '{resolved}'")
    return gateway
