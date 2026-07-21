"""Host-only HttpOnly Web sessions and CSRF origin enforcement."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from app.config import settings


WEB_SESSION_COOKIE = "health_session"
WEB_SESSION_AUTH_SENTINEL = "__web_cookie_session__"
WEB_SESSION_TRANSPORT = "web-cookie"
WEB_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 365 * 2
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def wants_web_session(request: Request) -> bool:
    return request.headers.get("x-auth-transport", "").strip().lower() == WEB_SESSION_TRANSPORT


def set_web_session_cookie(
    response: Response,
    token: str,
    *,
    max_age: int = WEB_SESSION_MAX_AGE_SECONDS,
) -> None:
    response.set_cookie(
        key=WEB_SESSION_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=(settings.app_env or "").strip().lower() == "production",
        samesite="strict",
        path="/",
    )


def clear_web_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=WEB_SESSION_COOKIE,
        httponly=True,
        secure=(settings.app_env or "").strip().lower() == "production",
        samesite="strict",
        path="/",
    )


def _normalized_origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def enforce_cookie_request_origin(request: Request) -> None:
    """Reject cross-site and origin-less state changes made with a browser cookie."""
    if request.method.upper() in _SAFE_METHODS:
        return

    origin = _normalized_origin(request.headers.get("origin", ""))
    trusted = {
        normalized
        for item in settings.web_session_allowed_origins_list
        if (normalized := _normalized_origin(item))
    }
    if origin is None or origin not in trusted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Web 会话来源校验失败",
        )
