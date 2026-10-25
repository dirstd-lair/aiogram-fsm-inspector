from __future__ import annotations

import os
import secrets
from typing import Optional
from fastapi import HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security_bearer = HTTPBearer(auto_error=False)


class SecurityError(RuntimeError):
    """Raised when server binds to public host without auth token protection."""
    pass


def validate_host_security(host: str, auth_token: Optional[str] = None) -> None:
    """
    Prevents accidental production deployment on 0.0.0.0 without authentication.
    """
    is_loopback = host in ("127.0.0.1", "localhost", "::1", "testserver")
    is_unsafe_allowed = os.getenv("AIOGRAM_DEVTOOLS_UNSAFE", "0") == "1"

    if not is_loopback and not auth_token and not is_unsafe_allowed:
        raise SecurityError(
            f"Binding aiogram-devtools to public interface '{host}' without an 'auth_token' is prohibited. "
            "Please provide an auth_token='your_secret_token' in setup_devtools(), "
            "or set environment variable AIOGRAM_DEVTOOLS_UNSAFE=1 for local docker/testing."
        )


class TokenAuthValidator:
    """FastAPI dependency for verifying access token if configured."""

    def __init__(self, required_token: Optional[str] = None) -> None:
        self.required_token = required_token

    async def __call__(
        self,
        request: Request,
        token_query: Optional[str] = Query(None, alias="token"),
        bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    ) -> bool:
        if not self.required_token:
            return True

        provided_token: Optional[str] = None
        if bearer and bearer.credentials:
            provided_token = bearer.credentials
        elif token_query:
            provided_token = token_query
        elif "x-devtools-token" in request.headers:
            provided_token = request.headers["x-devtools-token"]

        if not provided_token or not secrets.compare_digest(provided_token, self.required_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing devtools authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return True

    def validate_ws_token(self, token_param: Optional[str]) -> bool:
        if not self.required_token:
            return True
        if not token_param:
            return False
        return secrets.compare_digest(token_param, self.required_token)
