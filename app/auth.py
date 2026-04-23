from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


PASSWORD_PREFIX = "scrypt"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "$".join(
        [
            PASSWORD_PREFIX,
            "16384",
            "8",
            "1",
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    parts = password_hash.split("$")
    if len(parts) != 6 or parts[0] != PASSWORD_PREFIX:
        return False
    _, n_value, r_value, p_value, salt_b64, digest_b64 = parts
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=int(n_value),
        r=int(r_value),
        p=int(p_value),
    )
    return hmac.compare_digest(expected, derived)


def authenticate_user(session: Session, login: str, password: str) -> Optional[User]:
    statement = select(User).where(User.login == login.strip())
    user = session.scalar(statement)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def login_user(request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_user(request) -> None:
    request.session.pop("user_id", None)


def is_admin(user: Optional[User]) -> bool:
    return bool(user and user.role == "admin")


def is_networker(user: Optional[User]) -> bool:
    return bool(user and user.role == "networker")

