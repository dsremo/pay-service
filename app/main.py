from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import service
from app.db import get_session, init_schema
from app.errors import ApiError
from app.schemas import CreatePaymentRequest, RefundRequest, VerifyPaymentRequest
from app.security import require_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="pay-service", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})

    @app.get("/")
    async def info() -> dict:
        return {
            "service": "pay-service",
            "endpoints": {
                "POST /api/payments": "create a payment (Idempotency-Key header; X-API-Key)",
                "GET /api/payments/{id}": "status + event history + refunds",
                "POST /api/payments/{id}/refund": "full or partial refund (X-API-Key)",
                "GET /api/refunds/{id}": "refund status",
                "POST /api/payments/{id}/mock/{approve|decline}": "drive the mock provider",
                "POST /api/verify-payment": "verify checkout signature",
                "POST /api/webhook": "gateway webhook (HMAC verified)",
            },
        }

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/api/payments", status_code=201, dependencies=[Depends(require_api_key)])
    async def create_payment(
        req: CreatePaymentRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        session: Session = Depends(get_session),
    ):
        return await service.create_payment(session, req, idempotency_key)

    @app.get("/api/payments/{payment_id}")
    async def get_payment(payment_id: str, session: Session = Depends(get_session)):
        return service.get_payment_status(session, payment_id)

    @app.post("/api/payments/{payment_id}/refund", status_code=201, dependencies=[Depends(require_api_key)])
    async def refund_payment(payment_id: str, req: RefundRequest, session: Session = Depends(get_session)):
        return await service.create_refund(session, payment_id, req)

    @app.get("/api/refunds/{refund_id}")
    async def get_refund(refund_id: str, session: Session = Depends(get_session)):
        return service.get_refund(session, refund_id)

    @app.post("/api/payments/{payment_id}/mock/{action}")
    async def mock_action(payment_id: str, action: str, session: Session = Depends(get_session)):
        if action not in ("approve", "decline"):
            raise ApiError(404, "not_found")
        return service.mock_action(session, payment_id, action)

    @app.post("/api/verify-payment")
    async def verify_payment(req: VerifyPaymentRequest, session: Session = Depends(get_session)):
        return await service.verify_payment(session, req)

    @app.post("/api/webhook")
    async def webhook(
        request: Request,
        x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
        session: Session = Depends(get_session),
    ):
        raw_body = await request.body()
        return await service.handle_webhook(session, raw_body, x_razorpay_signature or "")

    return app


app = create_app()
