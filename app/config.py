import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "sqlite:///./pay-service.db")
        self.payment_ttl_seconds = int(os.environ.get("PAYMENT_TTL_SECONDS", "600"))
        self.api_keys = {
            key.strip()
            for key in os.environ.get("PAY_API_KEYS", "").split(",")
            if key.strip()
        }
        self.razorpay_key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        self.razorpay_key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        self.razorpay_webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def auth_enabled(self) -> bool:
        return len(self.api_keys) > 0


settings = Settings()
