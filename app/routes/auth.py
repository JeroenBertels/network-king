from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import authenticate_user, login_user, logout_user
from app.utils import add_flash
from app.web import template_context


router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context=template_context(request, page_title="Log In"),
    )


@router.post("/login")
async def login_submit(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    session = request.app.state.session_factory()
    try:
        user = authenticate_user(session, login, password)
    finally:
        session.close()
    if user is None:
        add_flash(request, "error", "That login and password combination was not recognized.")
        return RedirectResponse("/login", status_code=303)
    login_user(request, user)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout_page(request: Request):
    logout_user(request)
    return RedirectResponse("/", status_code=303)
