# pay-service — UPI payment orchestrator (Python / FastAPI)

Production-shaped backend port of the payment orchestrator. Same domain as the JS/Workers
version (pay.dsremo.com), rebuilt in the stack the user is hired for: FastAPI + SQLAlchemy +
Alembic + Postgres/SQLite. Adds the patterns that were missing vs the JS demo:
**multi-gateway router** and **API-key auth**.

## Parts
- [x] 1. Skeleton + domain — config, db, models (Payment/PaymentEvent/Refund), enums, schemas
- [ ] 2. Gateway layer — PaymentGateway interface, MockGateway, RazorpayGateway, GatewayRouter (factory)
- [ ] 3. Services + API — state machine, idempotency, refunds, HMAC verify, controllers, webhook, API-key auth, error handling, app factory
- [ ] 4. Tests + README + Dockerfile -> remote build (HF Space, laptop-safe) -> push public repo -> portfolio/resumes

## Design notes
- Async throughout (FastAPI + httpx). SQLite by default; Postgres via DATABASE_URL.
- Provider chosen by config: razorpay when RAZORPAY_KEY_ID/SECRET set, else keyless mock.
- State machine enforced server-side (ALLOWED_TRANSITIONS); every transition logged to payment_events.
- Idempotency-Key header -> unique column. Refunds guarded so total can't exceed captured amount.
- Razorpay signature: HMAC-SHA256; webhook + checkout-callback both verified.
- API-key auth via dependency/middleware (PAY_API_KEYS env); disabled if unset (local/demo).
