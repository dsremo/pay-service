from datetime import datetime

from pydantic import BaseModel, Field


class CreatePaymentRequest(BaseModel):
    amount: int = Field(gt=0, description="amount in paise (minor units)")
    currency: str = "INR"
    vpa: str | None = None
    order_id: str | None = None
    metadata: dict | None = None


class RefundRequest(BaseModel):
    amount: int | None = Field(default=None, gt=0)
    reason: str | None = None


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class EventOut(BaseModel):
    type: str
    at: datetime
    data: dict | None = None


class RefundOut(BaseModel):
    id: str
    payment_id: str
    amount: int
    status: str
    provider_ref: str | None = None
    reason: str | None = None
    created_at: datetime
    updated_at: datetime


class PaymentOut(BaseModel):
    id: str
    status: str
    amount: int
    currency: str
    vpa: str | None = None
    provider: str
    order_id: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = None
    refunded_amount: int = 0
    refundable_amount: int = 0
    checkout: dict | None = None
    events: list[EventOut] | None = None
    refunds: list[RefundOut] | None = None
