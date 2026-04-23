from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.auth import hash_password
from app.database import Base, create_session_factory
from app.models import User
from app.settings import Settings, get_settings


def ensure_seed_admin(
    settings: Optional[Settings] = None,
    session_factory=None,
    engine=None,
) -> bool:
    settings = settings or get_settings()
    if not settings.seed_admin_login or not settings.seed_admin_password:
        return False
    if session_factory is None or engine is None:
        engine, session_factory = create_session_factory(settings)
    Base.metadata.create_all(bind=engine)
    session = session_factory()
    try:
        user = session.scalar(select(User).where(User.login == settings.seed_admin_login))
        if user is None:
            user = User(
                login=settings.seed_admin_login,
                display_name=settings.seed_admin_name,
                password_hash=hash_password(settings.seed_admin_password),
                role="admin",
            )
            session.add(user)
        else:
            user.display_name = settings.seed_admin_name
            user.password_hash = hash_password(settings.seed_admin_password)
            user.role = "admin"
        session.commit()
        return True
    finally:
        session.close()


if __name__ == "__main__":
    created = ensure_seed_admin()
    if created:
        print("Seed admin ensured.")
    else:
        print("Set SEED_ADMIN_LOGIN and SEED_ADMIN_PASSWORD to create the admin user.")
