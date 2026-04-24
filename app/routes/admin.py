from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import hash_password, is_admin
from app.badges import build_badge_zip
from app.models import Character, Event, EventMembership, User
from app.utils import add_flash, decode_payload, dump_csv, encode_payload, format_event_names, new_qr_token, parse_csv_text, parse_event_names, slugify
from app.web import current_user_from_request, template_context


router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_guard(request: Request):
    if not is_admin(current_user_from_request(request)):
        add_flash(request, "error", "Admin access is required for that page.")
        return RedirectResponse("/login", status_code=303)
    return None


def _load_events(session):
    statement = (
        select(Event)
        .options(
            selectinload(Event.characters),
            selectinload(Event.memberships).selectinload(EventMembership.user),
        )
        .order_by(Event.name.asc())
    )
    return session.scalars(statement).unique().all()


def _load_networkers(session):
    statement = (
        select(User)
        .where(User.role == "networker")
        .options(selectinload(User.memberships).selectinload(EventMembership.event))
        .order_by(User.login.asc())
    )
    return session.scalars(statement).unique().all()


def _load_event(session, event_id: int):
    statement = (
        select(Event)
        .where(Event.id == event_id)
        .options(
            selectinload(Event.characters),
            selectinload(Event.memberships).selectinload(EventMembership.user),
            selectinload(Event.notes),
        )
    )
    return session.scalar(statement)


def _render_events_page(request: Request, events, import_preview=None, import_errors=None):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="admin_events.html",
        context=template_context(
            request,
            page_title="Manage Events",
            events=events,
            import_preview=import_preview or [],
            import_errors=import_errors or [],
        ),
    )


def _render_networkers_page(request: Request, networkers, events, import_preview=None, import_errors=None):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="admin_networkers.html",
        context=template_context(
            request,
            page_title="Manage Networkers",
            networkers=networkers,
            events=events,
            import_preview=import_preview or [],
            import_errors=import_errors or [],
        ),
    )


def _render_characters_page(request: Request, event, import_preview=None, import_errors=None):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="admin_characters.html",
        context=template_context(
            request,
            page_title=f"Manage Characters for {event.name}",
            event=event,
            import_preview=import_preview or [],
            import_errors=import_errors or [],
        ),
    )


def _make_unique_slug(session, name: str) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 2
    while session.scalar(select(Event).where(Event.slug == slug)) is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _make_unique_qr_token(session) -> str:
    token = new_qr_token()
    while session.scalar(select(Character).where(Character.qr_token == token)) is not None:
        token = new_qr_token()
    return token


def _read_upload_text(upload: UploadFile, body: bytes) -> str:
    if not upload.filename:
        return ""
    return body.decode("utf-8-sig")


def _validate_events_csv(text: str, session) -> tuple[list[dict[str, Any]], list[str]]:
    rows = parse_csv_text(text)
    errors: list[str] = []
    preview: list[dict[str, Any]] = []
    if not rows:
        return [], ["The file did not contain any rows."]
    seen_names = set()
    existing_names = {event.name.lower() for event in _load_events(session)}
    for index, row in enumerate(rows, start=2):
        event_name = row.get("event_name", "").strip()
        if not event_name:
            errors.append(f"Row {index}: event_name is required.")
            continue
        normalized = event_name.lower()
        if normalized in seen_names:
            errors.append(f"Row {index}: duplicate event_name '{event_name}' in upload.")
            continue
        if normalized in existing_names:
            errors.append(f"Row {index}: event '{event_name}' already exists.")
            continue
        seen_names.add(normalized)
        preview.append({"event_name": event_name, "action": "create"})
    return preview, errors


def _validate_networkers_csv(text: str, session) -> tuple[list[dict[str, Any]], list[str]]:
    rows = parse_csv_text(text)
    errors: list[str] = []
    preview: list[dict[str, Any]] = []
    if not rows:
        return [], ["The file did not contain any rows."]

    event_lookup = {event.name.lower(): event for event in _load_events(session)}
    existing_users = {user.login.lower(): user for user in _load_networkers(session)}
    all_users = {user.login.lower(): user for user in session.scalars(select(User)).all()}
    seen_logins = set()
    for index, row in enumerate(rows, start=2):
        login = row.get("login", "").strip()
        display_name = row.get("name", "").strip() or login
        password = row.get("password", "")
        event_names = parse_event_names(row.get("event_names", ""))
        if not login:
            errors.append(f"Row {index}: login is required.")
            continue
        lowered = login.lower()
        if lowered in seen_logins:
            errors.append(f"Row {index}: duplicate login '{login}' in upload.")
            continue
        seen_logins.add(lowered)
        if lowered in all_users and lowered not in existing_users:
            errors.append(f"Row {index}: login '{login}' belongs to a non-networker account.")
            continue
        if lowered not in existing_users and not password.strip():
            errors.append(f"Row {index}: password is required for new networkers.")
            continue
        missing_events = [name for name in event_names if name.lower() not in event_lookup]
        if missing_events:
            errors.append(f"Row {index}: unknown event(s): {', '.join(missing_events)}.")
            continue
        preview.append(
            {
                "login": login,
                "name": display_name,
                "event_names": event_names,
                "password_supplied": bool(password.strip()),
                "action": "update" if lowered in existing_users else "create",
            }
        )
    return preview, errors


def _validate_characters_csv(text: str, session, event: Event) -> tuple[list[dict[str, Any]], list[str]]:
    rows = parse_csv_text(text)
    errors: list[str] = []
    preview: list[dict[str, Any]] = []
    if not rows:
        return [], ["The file did not contain any rows."]

    seen_positions = set()
    existing_by_position = {character.position: character for character in event.characters}
    for index, row in enumerate(rows, start=2):
        event_name = row.get("event_name", "").strip()
        position_value = row.get("position", "").strip()
        real_name = row.get("real_name", "").strip()
        fictional_name = row.get("fictional_name", "").strip()
        storyline_truth = row.get("storyline_truth", "").strip()

        if event_name.lower() != event.name.lower():
            errors.append(f"Row {index}: event_name must match '{event.name}'.")
            continue
        if not position_value.isdigit() or int(position_value) < 1:
            errors.append(f"Row {index}: position must be a positive integer.")
            continue
        position = int(position_value)
        if position in seen_positions:
            errors.append(f"Row {index}: duplicate position '{position}' in upload.")
            continue
        seen_positions.add(position)
        if not real_name or not fictional_name:
            errors.append(f"Row {index}: real_name and fictional_name are required.")
            continue
        preview.append(
            {
                "position": position,
                "real_name": real_name,
                "fictional_name": fictional_name,
                "storyline_truth": storyline_truth,
                "action": "update" if position in existing_by_position else "create",
            }
        )
    return preview, errors


@router.get("/events")
async def manage_events(request: Request):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        events = _load_events(session)
    finally:
        session.close()
    return _render_events_page(request, events)


@router.post("/events")
async def create_event(request: Request, name: str = Form(...)):
    if guard := _admin_guard(request):
        return guard
    cleaned_name = name.strip()
    if not cleaned_name:
        add_flash(request, "error", "Event name is required.")
        return RedirectResponse("/admin/events", status_code=303)
    session = request.app.state.session_factory()
    try:
        existing = session.scalar(select(Event).where(Event.name == cleaned_name))
        if existing is not None:
            add_flash(request, "error", "That event already exists.")
            return RedirectResponse("/admin/events", status_code=303)
        event = Event(name=cleaned_name, slug=_make_unique_slug(session, cleaned_name))
        session.add(event)
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Created event '{cleaned_name}'.")
    return RedirectResponse("/admin/events", status_code=303)


@router.post("/events/{event_id}/update")
async def update_event(request: Request, event_id: int, name: str = Form(...)):
    if guard := _admin_guard(request):
        return guard
    cleaned_name = name.strip()
    if not cleaned_name:
        add_flash(request, "error", "Event name is required.")
        return RedirectResponse("/admin/events", status_code=303)
    session = request.app.state.session_factory()
    try:
        event = session.get(Event, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        duplicate = session.scalar(select(Event).where(Event.name == cleaned_name, Event.id != event_id))
        if duplicate is not None:
            add_flash(request, "error", "Another event already uses that name.")
            return RedirectResponse("/admin/events", status_code=303)
        event.name = cleaned_name
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", "Event updated.")
    return RedirectResponse("/admin/events", status_code=303)


@router.post("/events/{event_id}/delete")
async def delete_event(request: Request, event_id: int):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        event = _load_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        event_name = event.name
        session.delete(event)
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Deleted event '{event_name}'.")
    return RedirectResponse("/admin/events", status_code=303)


@router.get("/events/export")
async def export_events(request: Request):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        rows = [{"event_name": event.name} for event in _load_events(session)]
    finally:
        session.close()
    content = dump_csv(rows, ["event_name"])
    headers = {"Content-Disposition": 'attachment; filename="events.csv"'}
    return Response(content=content, media_type="text/csv", headers=headers)


@router.post("/events/import/validate")
async def validate_events_import(request: Request, csv_file: UploadFile = File(...)):
    if guard := _admin_guard(request):
        return guard
    body = await csv_file.read()
    text = _read_upload_text(csv_file, body)
    session = request.app.state.session_factory()
    try:
        events = _load_events(session)
        preview, errors = _validate_events_csv(text, session)
    finally:
        session.close()
    payload = encode_payload(text) if preview and not errors else ""
    for row in preview:
        row["payload"] = payload
    return _render_events_page(request, events, import_preview=preview if not errors else [], import_errors=errors)


@router.post("/events/import/commit")
async def commit_events_import(request: Request, import_payload: str = Form(...)):
    if guard := _admin_guard(request):
        return guard
    text = decode_payload(import_payload)
    session = request.app.state.session_factory()
    try:
        preview, errors = _validate_events_csv(text, session)
        if errors:
            events = _load_events(session)
            return _render_events_page(request, events, import_errors=errors)
        for row in preview:
            session.add(Event(name=row["event_name"], slug=_make_unique_slug(session, row["event_name"])))
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Imported {len(preview)} event(s).")
    return RedirectResponse("/admin/events", status_code=303)


@router.get("/networkers")
async def manage_networkers(request: Request):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        networkers = _load_networkers(session)
        events = _load_events(session)
    finally:
        session.close()
    return _render_networkers_page(request, networkers, events)


@router.post("/networkers")
async def create_networker(
    request: Request,
    login: str = Form(...),
    name: str = Form(""),
    password: str = Form(...),
    event_ids: list[int] = Form(default=[]),
):
    if guard := _admin_guard(request):
        return guard
    cleaned_login = login.strip()
    display_name = name.strip() or cleaned_login
    if not cleaned_login or not password.strip():
        add_flash(request, "error", "Login and password are required.")
        return RedirectResponse("/admin/networkers", status_code=303)
    session = request.app.state.session_factory()
    try:
        if session.scalar(select(User).where(User.login == cleaned_login)) is not None:
            add_flash(request, "error", "That login is already in use.")
            return RedirectResponse("/admin/networkers", status_code=303)
        user = User(
            login=cleaned_login,
            display_name=display_name,
            password_hash=hash_password(password.strip()),
            role="networker",
        )
        session.add(user)
        session.flush()
        for event_id in event_ids:
            session.add(EventMembership(user_id=user.id, event_id=event_id))
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Created networker '{cleaned_login}'.")
    return RedirectResponse("/admin/networkers", status_code=303)


@router.post("/networkers/{user_id}/update")
async def update_networker(
    request: Request,
    user_id: int,
    name: str = Form(""),
    password: str = Form(""),
    event_ids: list[int] = Form(default=[]),
):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        user = session.scalar(select(User).where(User.id == user_id, User.role == "networker").options(selectinload(User.memberships)))
        if user is None:
            raise HTTPException(status_code=404, detail="Networker not found.")
        user.display_name = name.strip() or user.login
        if password.strip():
            user.password_hash = hash_password(password.strip())
        existing_event_ids = {membership.event_id for membership in user.memberships}
        desired_event_ids = set(event_ids)
        for membership in list(user.memberships):
            if membership.event_id not in desired_event_ids:
                session.delete(membership)
        for event_id in desired_event_ids - existing_event_ids:
            session.add(EventMembership(user_id=user.id, event_id=event_id))
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", "Networker updated.")
    return RedirectResponse("/admin/networkers", status_code=303)


@router.post("/networkers/{user_id}/delete")
async def delete_networker(request: Request, user_id: int):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        user = session.scalar(select(User).where(User.id == user_id, User.role == "networker"))
        if user is None:
            raise HTTPException(status_code=404, detail="Networker not found.")
        login = user.login
        session.delete(user)
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Deleted networker '{login}'.")
    return RedirectResponse("/admin/networkers", status_code=303)


@router.get("/networkers/export")
async def export_networkers(request: Request):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        rows = []
        for networker in _load_networkers(session):
            event_names = [membership.event.name for membership in networker.memberships]
            rows.append(
                {
                    "login": networker.login,
                    "name": networker.display_name,
                    "event_names": format_event_names(event_names),
                }
            )
    finally:
        session.close()
    content = dump_csv(rows, ["login", "name", "event_names"])
    headers = {"Content-Disposition": 'attachment; filename="networkers.csv"'}
    return Response(content=content, media_type="text/csv", headers=headers)


@router.post("/networkers/import/validate")
async def validate_networkers_import(request: Request, csv_file: UploadFile = File(...)):
    if guard := _admin_guard(request):
        return guard
    body = await csv_file.read()
    text = _read_upload_text(csv_file, body)
    session = request.app.state.session_factory()
    try:
        networkers = _load_networkers(session)
        events = _load_events(session)
        preview, errors = _validate_networkers_csv(text, session)
    finally:
        session.close()
    payload = encode_payload(text) if preview and not errors else ""
    for row in preview:
        row["payload"] = payload
    return _render_networkers_page(request, networkers, events, import_preview=preview if not errors else [], import_errors=errors)


@router.post("/networkers/import/commit")
async def commit_networkers_import(request: Request, import_payload: str = Form(...)):
    if guard := _admin_guard(request):
        return guard
    text = decode_payload(import_payload)
    session = request.app.state.session_factory()
    try:
        preview, errors = _validate_networkers_csv(text, session)
        if errors:
            networkers = _load_networkers(session)
            events = _load_events(session)
            return _render_networkers_page(request, networkers, events, import_errors=errors)
        event_lookup = {event.name.lower(): event for event in _load_events(session)}
        for row in preview:
            login = row["login"]
            user = session.scalar(select(User).where(User.login == login))
            if user is None:
                user = User(
                    login=login,
                    display_name=row["name"] or login,
                    password_hash=hash_password("placeholder"),
                    role="networker",
                )
                session.add(user)
                session.flush()
            user.display_name = row["name"] or login
            original_rows = next(item for item in parse_csv_text(text) if item.get("login", "").strip().lower() == login.lower())
            password = original_rows.get("password", "").strip()
            if password:
                user.password_hash = hash_password(password)
            desired_events = {event_lookup[name.lower()].id for name in row["event_names"]}
            existing_memberships = session.scalars(select(EventMembership).where(EventMembership.user_id == user.id)).all()
            existing_event_ids = {membership.event_id for membership in existing_memberships}
            for membership in existing_memberships:
                if membership.event_id not in desired_events:
                    session.delete(membership)
            for event_id in desired_events - existing_event_ids:
                session.add(EventMembership(user_id=user.id, event_id=event_id))
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Imported {len(preview)} networker row(s).")
    return RedirectResponse("/admin/networkers", status_code=303)


@router.get("/events/{event_id}/characters")
async def manage_characters(request: Request, event_id: int):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        event = _load_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
    finally:
        session.close()
    return _render_characters_page(request, event)


@router.post("/events/{event_id}/characters")
async def create_character(
    request: Request,
    event_id: int,
    position: int = Form(...),
    real_name: str = Form(...),
    fictional_name: str = Form(...),
    storyline_truth: str = Form(""),
):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        event = session.get(Event, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        duplicate = session.scalar(select(Character).where(Character.event_id == event_id, Character.position == position))
        if duplicate is not None:
            add_flash(request, "error", "That event already has a character at that position.")
            return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)
        character = Character(
            event_id=event_id,
            position=position,
            real_name=real_name.strip(),
            fictional_name=fictional_name.strip(),
            storyline_truth=storyline_truth.strip(),
            qr_token=_make_unique_qr_token(session),
        )
        session.add(character)
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", "Character created.")
    return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)


@router.post("/events/{event_id}/characters/{character_id}/update")
async def update_character(
    request: Request,
    event_id: int,
    character_id: int,
    position: int = Form(...),
    real_name: str = Form(...),
    fictional_name: str = Form(...),
    storyline_truth: str = Form(""),
):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        character = session.scalar(select(Character).where(Character.id == character_id, Character.event_id == event_id))
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        duplicate = session.scalar(
            select(Character).where(
                Character.event_id == event_id,
                Character.position == position,
                Character.id != character_id,
            )
        )
        if duplicate is not None:
            add_flash(request, "error", "Another character already uses that position.")
            return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)
        character.position = position
        character.real_name = real_name.strip()
        character.fictional_name = fictional_name.strip()
        character.storyline_truth = storyline_truth.strip()
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", "Character updated.")
    return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)


@router.post("/events/{event_id}/characters/{character_id}/delete")
async def delete_character(request: Request, event_id: int, character_id: int):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        character = session.scalar(select(Character).where(Character.id == character_id, Character.event_id == event_id))
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        fictional_name = character.fictional_name
        session.delete(character)
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Deleted character '{fictional_name}'.")
    return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)


@router.post("/events/{event_id}/characters/{character_id}/image")
async def upload_character_image(request: Request, event_id: int, character_id: int, image: UploadFile = File(...)):
    if guard := _admin_guard(request):
        return guard
    if not image.filename:
        add_flash(request, "error", "Choose an image before uploading.")
        return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)
    body = await image.read()
    session = request.app.state.session_factory()
    try:
        character = session.scalar(select(Character).where(Character.id == character_id, Character.event_id == event_id))
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        character.image_key = request.app.state.storage.save_bytes(body, image.filename)
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", "Profile image uploaded.")
    return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)


@router.get("/events/{event_id}/characters/export")
async def export_characters(request: Request, event_id: int):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        event = _load_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        networkers = sorted(
            [membership.user for membership in event.memberships if membership.user.role == "networker"],
            key=lambda user: user.login.lower(),
        )
        note_by_character_and_user = {
            (note.character_id, note.user_id): note.note_text
            for note in event.notes
            if note.note_text.strip()
        }
        fieldnames = ["event_name", "position", "real_name", "fictional_name", "storyline_truth"] + [
            f"note__{networker.login}" for networker in networkers
        ]
        rows = []
        for character in sorted(event.characters, key=lambda item: item.position):
            row = {
                "event_name": event.name,
                "position": str(character.position),
                "real_name": character.real_name,
                "fictional_name": character.fictional_name,
                "storyline_truth": character.storyline_truth,
            }
            for networker in networkers:
                row[f"note__{networker.login}"] = note_by_character_and_user.get((character.id, networker.id), "")
            rows.append(row)
    finally:
        session.close()
    content = dump_csv(rows, fieldnames)
    headers = {"Content-Disposition": f'attachment; filename="{event.slug}-characters.csv"'}
    return Response(content=content, media_type="text/csv", headers=headers)


@router.post("/events/{event_id}/characters/import/validate")
async def validate_characters_import(request: Request, event_id: int, csv_file: UploadFile = File(...)):
    if guard := _admin_guard(request):
        return guard
    body = await csv_file.read()
    text = _read_upload_text(csv_file, body)
    session = request.app.state.session_factory()
    try:
        event = _load_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        preview, errors = _validate_characters_csv(text, session, event)
    finally:
        session.close()
    payload = encode_payload(text) if preview and not errors else ""
    for row in preview:
        row["payload"] = payload
    return _render_characters_page(request, event, import_preview=preview if not errors else [], import_errors=errors)


@router.post("/events/{event_id}/characters/import/commit")
async def commit_characters_import(request: Request, event_id: int, import_payload: str = Form(...)):
    if guard := _admin_guard(request):
        return guard
    text = decode_payload(import_payload)
    session = request.app.state.session_factory()
    try:
        event = _load_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        preview, errors = _validate_characters_csv(text, session, event)
        if errors:
            return _render_characters_page(request, event, import_errors=errors)
        existing_by_position = {character.position: character for character in event.characters}
        for row in preview:
            character = existing_by_position.get(row["position"])
            if character is None:
                character = Character(
                    event_id=event_id,
                    position=row["position"],
                    real_name=row["real_name"],
                    fictional_name=row["fictional_name"],
                    storyline_truth=row["storyline_truth"],
                    qr_token=_make_unique_qr_token(session),
                )
                session.add(character)
            else:
                character.position = row["position"]
                character.real_name = row["real_name"]
                character.fictional_name = row["fictional_name"]
                character.storyline_truth = row["storyline_truth"]
        session.commit()
    finally:
        session.close()
    add_flash(request, "success", f"Imported {len(preview)} character row(s).")
    return RedirectResponse(f"/admin/events/{event_id}/characters", status_code=303)


@router.get("/events/{event_id}/characters/badges.zip")
async def download_badges(request: Request, event_id: int):
    if guard := _admin_guard(request):
        return guard
    session = request.app.state.session_factory()
    try:
        event = _load_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        payload = build_badge_zip(
            sorted(event.characters, key=lambda item: item.position),
            request.app.state.settings.app_base_url,
            event.name,
        )
    finally:
        session.close()
    headers = {"Content-Disposition": f'attachment; filename="{event.slug}-badges.zip"'}
    return Response(content=payload, media_type="application/zip", headers=headers)
