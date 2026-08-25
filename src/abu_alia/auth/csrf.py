from __future__ import annotations

import hmac
import secrets
from typing import Optional

from fastapi import HTTPException, Request
from starlette.responses import Response

from abu_alia.config import get_settings

COOKIE = "abu_alia_csrf"
FORM_FIELD = "csrf_token"
HEADER = "x-csrf-token"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def token_for_request(request: Request) -> str:
    existing = request.cookies.get(COOKIE) or getattr(request.state, "csrf_token", None)
    if existing:
        request.state.csrf_token = existing
        return existing
    token = new_csrf_token()
    request.state.csrf_token = token
    return token


def set_csrf_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.session_days * 86400,
        path="/",
    )


def _extract_submitted(request: Request, form_token: Optional[str]) -> Optional[str]:
    header = request.headers.get(HEADER)
    if header:
        return header
    if form_token:
        return str(form_token)
    return None


async def csrf_protect(request: Request) -> None:
    cookie = request.cookies.get(COOKIE) or getattr(request.state, "csrf_token", None)
    form_token = None
    content_type = request.headers.get("content-type", "")
    if "form" in content_type:
        form = await request.form()
        form_token = form.get(FORM_FIELD)
    submitted = _extract_submitted(request, form_token if isinstance(form_token, str) else None)
    if not cookie or not submitted or not hmac.compare_digest(cookie, submitted):
        raise HTTPException(status_code=403, detail="رمز الحماية غير صالح")
