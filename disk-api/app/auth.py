"""API Key authentication dependency for all protected routes."""
import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key_query = APIKeyQuery(name="key", auto_error=False)

_API_KEY = os.environ.get("DISK_API_KEY", "")


async def require_api_key(
    api_key_header: str | None = Security(_api_key_header),
    api_key_query: str | None = Security(_api_key_query),
) -> None:
    if not _API_KEY:
        raise RuntimeError("DISK_API_KEY environment variable is not set")
    api_key = api_key_header or api_key_query
    if api_key != _API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
