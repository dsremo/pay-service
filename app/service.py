import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.enums import ALLOWED_TRANSITIONS, PaymentStatus, RefundStatus
from app.errors import ApiError
from app.gateways.router import default_gateway_name, get_gateway
from app.models import Payment, PaymentEvent, Refund
from app.schemas import (
    CreatePaymentRequest,
    EventOut,
    PaymentOut,
    RefundOut,
    RefundRequest,
    VerifyPaymentRequest,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hmac_sha256_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def log_event(session: Session, payment_id: str, event_type: str, data: dict | None = None) -> None:
    session.add(
        PaymentEvent(
            payment_id=payment_id,
            at=_now(),
            type=event_type,
            data=json.dumps(data) if data is not None else None,
        )
    )


def transition(
    session: Session,
    payment: Payment,
    to_status: PaymentStatus,
    event_type: str,
    data: dict | None = None,
) -> None:
    allowed = ALLOWED_TRANSITIONS[PaymentStatus(payment.status)]
    if to_status not in allowed:
        raise ApiError(500, "illegal_transition", f"{payment.status} -> {to_status.value}")
    from_status = payment.status
    timestamp = _now()
    result = session.execute(
        update(Payment)
        .where(Payment.id == payment.id, Payment.status == from_status)
        .values(status=to_status.value, updated_at=timestamp)
    )
    if result.rowcount == 0:
        raise ApiError(409, "transition_race", f"{from_status} -> {to_status.value}")
    payment.status = to_status.value
    payment.updated_at = timestamp
    log_event(session, payment.id, event_type, data)


def _load(session: Session, payment_id: str) -> Payment | None:
    return session.get(Payment, payment_id)


def _load_with_expiry(session: Session, payment_id: str) -> Payment | None:
    payment = _load(session, payment_id)
    if payment is None:
        return None
    if payment.status in (PaymentStatus.CREATED.value, PaymentStatus.PENDING.value):
        created = payment.created_at if payment.created_at.tzinfo else payment.created_at.replace(tzinfo=timezone.utc)
        age = (_now() - created).total_seconds()
        if age > settings.payment_ttl_seconds:
            transition(session, payment, PaymentStatus.EXPIRED, "payment.expired", {"ttl_seconds": settings.payment_ttl_seconds})
            session.commit()
    return payment


async def create_payment(session: Session, req: CreatePaymentRequest, idempotency_key: str | None) -> PaymentOut:
    if idempotency_key:
        existing = session.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if existing is not None:
            return _payment_out(session, existing)

    provider = default_gateway_name()
    payment_id = "pay_" + uuid.uuid4().hex
    timestamp = _now()
    payment = Payment(
        id=payment_id,
        created_at=timestamp,
        updated_at=timestamp,
        amount=req.amount,
        currency=req.currency,
        vpa=req.vpa,
        status=PaymentStatus.CREATED.value,
        provider=provider,
        provider_ref=None,
        order_id=req.order_id,
        idempotency_key=idempotency_key,
        meta=json.dumps(req.metadata) if req.metadata else None,
        refunded_amount=0,
    )
    session.add(payment)
    session.flush()
    log_event(session, payment_id, "payment.created", {"amount": req.amount, "currency": req.currency, "provider": provider})

    gateway = get_gateway(provider)
    order = await gateway.create_order(req.amount, req.currency, payment_id)
    payment.provider_ref = order.order_ref
    event_type = "razorpay.order.created" if provider == "razorpay" else "collect.sent"
    transition(session, payment, PaymentStatus.PENDING, event_type, {"order_ref": order.order_ref})
    session.commit()
    return _payment_out(session, payment)


def get_payment_status(session: Session, payment_id: str) -> PaymentOut:
    payment = _load_with_expiry(session, payment_id)
    if payment is None:
        raise ApiError(404, "not_found")
    return _payment_out(session, payment, detail=True)


def mock_action(session: Session, payment_id: str, action: str) -> PaymentOut:
    payment = _load_with_expiry(session, payment_id)
    if payment is None:
        raise ApiError(404, "not_found")
    if payment.provider != "mock":
        raise ApiError(400, "unsupported", "mock actions apply only to mock-provider payments")
    if payment.status != PaymentStatus.PENDING.value:
        raise ApiError(409, "invalid_state", f"cannot {action} a payment in status '{payment.status}'")
    to_status = PaymentStatus.SUCCESS if action == "approve" else PaymentStatus.FAILED
    event_type = "payment.success" if action == "approve" else "payment.failed"
    transition(session, payment, to_status, event_type, {"via": "mock_payer_action"})
    session.commit()
    return _payment_out(session, payment)


async def verify_payment(session: Session, req: VerifyPaymentRequest) -> dict:
    if not settings.razorpay_key_secret:
        raise ApiError(503, "not_configured")
    expected = _hmac_sha256_hex(settings.razorpay_key_secret, f"{req.razorpay_order_id}|{req.razorpay_payment_id}")
    if not hmac.compare_digest(expected, req.razorpay_signature):
        raise ApiError(400, "signature_mismatch")
    payment = session.scalar(select(Payment).where(Payment.provider_ref == req.razorpay_order_id))
    if payment is None:
        return {"verified": True, "note": "signature valid but no matching local payment"}
    payment.provider_payment_ref = req.razorpay_payment_id
    log_event(session, payment.id, "checkout.verified", {"razorpay_payment_id": req.razorpay_payment_id})
    if payment.status == PaymentStatus.PENDING.value:
        transition(session, payment, PaymentStatus.SUCCESS, "payment.success", {"via": "checkout_signature"})
    session.commit()
    return {"verified": True, "status": "success", "id": payment.id}


async def handle_webhook(session: Session, raw_body: bytes, signature: str) -> dict:
    if not settings.razorpay_webhook_secret:
        raise ApiError(503, "webhook_not_configured")
    expected = _hmac_sha256_hex(settings.razorpay_webhook_secret, raw_body.decode())
    if not hmac.compare_digest(expected, signature or ""):
        raise ApiError(401, "invalid_signature")
    event = json.loads(raw_body.decode())
    event_type = event.get("event", "unknown")
    entity = (event.get("payload", {}).get("payment", {}) or {}).get("entity", {})
    order_ref = entity.get("order_id")
    if not order_ref:
        return {"received": True, "note": "no order_id; ignored"}
    payment = session.scalar(select(Payment).where(Payment.provider_ref == order_ref))
    if payment is None:
        return {"received": True, "note": "no matching payment; ignored"}
    if payment.provider_payment_ref is None:
        payment.provider_payment_ref = entity.get("id")
    log_event(session, payment.id, "webhook." + event_type, {"razorpay_payment_id": entity.get("id")})
    if payment.status == PaymentStatus.PENDING.value:
        if event_type == "payment.captured":
            transition(session, payment, PaymentStatus.SUCCESS, "payment.success", {"via": "razorpay_webhook"})
        elif event_type == "payment.failed":
            transition(session, payment, PaymentStatus.FAILED, "payment.failed", {"via": "razorpay_webhook"})
    session.commit()
    return {"received": True}


async def create_refund(session: Session, payment_id: str, req: RefundRequest) -> RefundOut:
    payment = _load(session, payment_id)
    if payment is None:
        raise ApiError(404, "not_found")
    if payment.status != PaymentStatus.SUCCESS.value:
        raise ApiError(409, "invalid_state", f"only successful payments can be refunded (status '{payment.status}')")

    refundable = payment.amount - (payment.refunded_amount or 0)
    amount = req.amount if req.amount is not None else refundable
    if amount <= 0:
        raise ApiError(400, "invalid_amount", "refund amount must be a positive integer in paise")
    if amount > refundable:
        raise ApiError(400, "amount_exceeds_refundable", f"refundable is {refundable} paise")

    refund_id = "rfnd_" + uuid.uuid4().hex
    timestamp = _now()
    refund = Refund(
        id=refund_id,
        payment_id=payment_id,
        created_at=timestamp,
        updated_at=timestamp,
        amount=amount,
        status=RefundStatus.PROCESSING.value,
        provider_ref=None,
        reason=req.reason,
    )
    session.add(refund)
    log_event(session, payment_id, "refund.created", {"refund_id": refund_id, "amount": amount})
    session.commit()

    gateway_refund_ref = None
    try:
        if payment.provider == "razorpay":
            if not payment.provider_payment_ref:
                _fail_refund(session, refund, payment_id, "gateway payment id not captured")
                raise ApiError(409, "not_refundable", "gateway payment id not captured; verify the payment first")
            result = await get_gateway("razorpay").refund(payment.provider_payment_ref, amount)
            gateway_refund_ref = result.refund_ref
    except ApiError:
        raise
    except Exception as failure:  # noqa: BLE001
        _fail_refund(session, refund, payment_id, str(failure))
        raise ApiError(502, "gateway_refund_failed")

    bump = session.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.amount - Payment.refunded_amount >= amount)
        .values(refunded_amount=Payment.refunded_amount + amount, updated_at=_now())
    )
    if bump.rowcount == 0:
        _fail_refund(session, refund, payment_id, "refundable amount changed (concurrent refund)")
        raise ApiError(409, "refund_race", "refundable amount changed; retry")

    refund.status = RefundStatus.PROCESSED.value
    refund.provider_ref = gateway_refund_ref
    refund.updated_at = _now()
    log_event(session, payment_id, "refund.processed", {"refund_id": refund_id, "amount": amount, "gateway_refund": gateway_refund_ref})
    session.commit()
    return _refund_out(refund)


def _fail_refund(session: Session, refund: Refund, payment_id: str, reason: str) -> None:
    refund.status = RefundStatus.FAILED.value
    refund.updated_at = _now()
    log_event(session, payment_id, "refund.failed", {"refund_id": refund.id, "reason": reason})
    session.commit()


def get_refund(session: Session, refund_id: str) -> RefundOut:
    refund = session.get(Refund, refund_id)
    if refund is None:
        raise ApiError(404, "not_found")
    return _refund_out(refund)


def _refund_out(refund: Refund) -> RefundOut:
    return RefundOut(
        id=refund.id,
        payment_id=refund.payment_id,
        amount=refund.amount,
        status=refund.status,
        provider_ref=refund.provider_ref,
        reason=refund.reason,
        created_at=refund.created_at,
        updated_at=refund.updated_at,
    )


def _payment_out(session: Session, payment: Payment, detail: bool = False) -> PaymentOut:
    refundable = payment.amount - (payment.refunded_amount or 0) if payment.status == PaymentStatus.SUCCESS.value else 0
    checkout = None
    if payment.provider == "razorpay" and payment.provider_ref:
        checkout = {"razorpay_order_id": payment.provider_ref, "razorpay_key_id": settings.razorpay_key_id or None}

    events = None
    refunds = None
    if detail:
        event_rows = session.scalars(
            select(PaymentEvent).where(PaymentEvent.payment_id == payment.id).order_by(PaymentEvent.id)
        ).all()
        events = [
            EventOut(type=row.type, at=row.at, data=json.loads(row.data) if row.data else None)
            for row in event_rows
        ]
        refund_rows = session.scalars(
            select(Refund).where(Refund.payment_id == payment.id).order_by(Refund.created_at)
        ).all()
        refunds = [_refund_out(row) for row in refund_rows]

    return PaymentOut(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        vpa=payment.vpa,
        provider=payment.provider,
        order_id=payment.order_id,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        metadata=json.loads(payment.meta) if payment.meta else None,
        refunded_amount=payment.refunded_amount or 0,
        refundable_amount=refundable,
        checkout=checkout,
        events=events,
        refunds=refunds,
    )
