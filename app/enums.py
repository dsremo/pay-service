from enum import Enum


class PaymentStatus(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    EXPIRED = "expired"


class RefundStatus(str, Enum):
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


ALLOWED_TRANSITIONS = {
    PaymentStatus.CREATED: {PaymentStatus.PENDING, PaymentStatus.FAILED, PaymentStatus.EXPIRED},
    PaymentStatus.PENDING: {PaymentStatus.SUCCESS, PaymentStatus.FAILED, PaymentStatus.EXPIRED},
    PaymentStatus.SUCCESS: set(),
    PaymentStatus.FAILED: set(),
    PaymentStatus.EXPIRED: set(),
}
