from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import is_admin
from app.database import Base, create_session_factory
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.public import router as public_router
from app.seed_admin import ensure_seed_admin
from app.settings import Settings, get_settings
from app.storage import StorageService
from app.web import current_user_from_request


APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=app.state.engine)
    ensure_seed_admin(settings=app.state.settings, session_factory=app.state.session_factory, engine=app.state.engine)
    yield


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    engine, session_factory = create_session_factory(settings)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
    app.state.storage = StorageService(settings)

    app.state.templates.env.filters["datetime_label"] = lambda value: value.strftime("%d %b %Y %H:%M") if value else "Not yet"

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )

    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.get("/healthz")
    async def healthcheck():
        return {"status": "ok"}

    @app.get("/admin")
    async def admin_home(request: Request):
        if not is_admin(current_user_from_request(request)):
            return RedirectResponse("/", status_code=303)
        return RedirectResponse("/admin/events", status_code=303)

    app.include_router(auth_router)
    app.include_router(public_router)
    app.include_router(admin_router)
    return app


app = create_app()
