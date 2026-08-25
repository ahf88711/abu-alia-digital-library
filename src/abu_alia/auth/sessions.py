from __future__ import annotations

from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import Response

from abu_alia.config import get_settings

COOKIE = "abu_alia_session"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="session")


def set_session(response: Response, user_id: int) -> None:
    settings = get_settings()
    token = _serializer().dumps({"uid": user_id})
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.session_days * 86400,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def user_id_from_request(request: Request) -> Optional[int]:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    settings = get_settings()
    try:
        data = _serializer().loads(token, max_age=settings.session_days * 86400)
        return int(data.get("uid"))
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
