from fastapi import Header, HTTPException

from app.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.auth_enabled:
        return
    if x_api_key is None or x_api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="invalid_or_missing_api_key")
