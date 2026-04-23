from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from sqlalchemy import select

from app.auth import is_admin
from app.models import User
from app.utils import pop_flashes


def current_user_from_request(request: Request) -> Optional[User]:
    cached = getattr(request.state, "_current_user_cached", False)
    if cached:
        return getattr(request.state, "current_user", None)

    request.state._current_user_cached = True
    request.state.current_user = None

    if "session" not in request.scope:
        return None

    user_id = request.session.get("user_id")
    if not user_id:
        return None

    session = request.app.state.session_factory()
    try:
        user = session.scalar(select(User).where(User.id == user_id))
        request.state.current_user = user
        return user
    finally:
        session.close()


def template_context(request: Request, **context: Any) -> dict[str, Any]:
    current_user = current_user_from_request(request)
    return {
        "request": request,
        "current_user": current_user,
        "is_admin": is_admin(current_user),
        "flash_messages": pop_flashes(request),
        **context,
    }
