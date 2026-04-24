from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import is_admin
from app.gameplay import (
    build_progress_state,
    can_access_character,
    can_reveal_character,
    leaderboard_for_event,
    user_in_event,
)
from app.models import Character, CharacterNote, Event, EventMembership, User
from app.utils import add_flash, extract_qr_token
from app.web import current_user_from_request, template_context


router = APIRouter()


def _load_events(session):
    statement = (
        select(Event)
        .options(
            selectinload(Event.characters),
            selectinload(Event.memberships).selectinload(EventMembership.user),
            selectinload(Event.notes),
        )
        .order_by(Event.name.asc())
    )
    return session.scalars(statement).unique().all()


def _load_event_by_slug(session, slug: str):
    statement = (
        select(Event)
        .where(Event.slug == slug)
        .options(
            selectinload(Event.characters),
            selectinload(Event.memberships).selectinload(EventMembership.user),
            selectinload(Event.notes),
        )
    )
    return session.scalar(statement)


def _load_character_by_token(session, qr_token: str):
    statement = (
        select(Character)
        .where(Character.qr_token == qr_token)
        .options(
            selectinload(Character.event).selectinload(Event.characters),
            selectinload(Character.event).selectinload(Event.memberships).selectinload(EventMembership.user),
            selectinload(Character.event).selectinload(Event.notes),
        )
    )
    return session.scalar(statement)


def _find_character(event: Event, character_id: int):
    for character in event.characters:
        if character.id == character_id:
            return character
    return None


def _notes_for_user(event: Event, user: User):
    return [note for note in event.notes if note.user_id == user.id]


def _ensure_character_discovery(session, user: User, event: Event, character: Character):
    existing_note = session.scalar(
        select(CharacterNote).where(
            CharacterNote.user_id == user.id,
            CharacterNote.character_id == character.id,
        )
    )
    if existing_note is not None:
        return

    session.add(
        CharacterNote(
            user_id=user.id,
            event_id=event.id,
            character_id=character.id,
            note_text="",
        )
    )
    session.commit()


def _build_character_cards(event: Event, request: Request):
    current_user = current_user_from_request(request)
    note_lookup = {}
    progress_state = None
    if current_user and user_in_event(current_user, event):
        user_notes = _notes_for_user(event, current_user)
        progress_state = build_progress_state(list(event.characters), user_notes)
        note_lookup = progress_state.note_by_character_id
    cards = []
    for character in event.characters:
        accessible = bool(progress_state and can_access_character(current_user, character, progress_state))
        completed = bool(progress_state and character.id in progress_state.note_by_character_id)
        revealed = bool(progress_state and can_reveal_character(current_user, character, progress_state))
        cards.append(
            {
                "character": character,
                "accessible": accessible or is_admin(current_user),
                "completed": completed,
                "show_name": accessible or is_admin(current_user),
                "show_revealed_actions": revealed or is_admin(current_user),
                "is_current_unlock": bool(progress_state and character.position == progress_state.unlocked_position and not completed),
                "note": note_lookup.get(character.id),
            }
        )
    return cards, progress_state


@router.get("/")
async def landing_page(request: Request):
    session = request.app.state.session_factory()
    try:
        events = _load_events(session)
        leaderboard_map = {event.id: leaderboard_for_event(event)[:3] for event in events}
    finally:
        session.close()
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context=template_context(
            request,
            page_title="Network Events",
            events=events,
            leaderboard_map=leaderboard_map,
        ),
    )


@router.get("/events/{slug}")
async def event_page(request: Request, slug: str):
    session = request.app.state.session_factory()
    try:
        event = _load_event_by_slug(session, slug)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        character_cards, progress_state = _build_character_cards(event, request)
        leaderboard = leaderboard_for_event(event)
    finally:
        session.close()
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="event_detail.html",
        context=template_context(
            request,
            page_title=event.name,
            event=event,
            character_cards=character_cards,
            leaderboard=leaderboard,
            progress_state=progress_state,
            viewer_is_member=user_in_event(current_user_from_request(request), event),
        ),
    )


@router.get("/events/{slug}/scan")
async def scan_page(request: Request, slug: str):
    session = request.app.state.session_factory()
    try:
        event = _load_event_by_slug(session, slug)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
    finally:
        session.close()
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="scan.html",
        context=template_context(
            request,
            page_title=f"Scan for {event.name}",
            event=event,
        ),
    )


@router.post("/events/{slug}/scan")
async def scan_submit(request: Request, slug: str, qr_value: str = Form(...)):
    token = extract_qr_token(qr_value)
    if not token:
        add_flash(request, "error", "Paste or scan a QR value first.")
        return RedirectResponse(f"/events/{slug}/scan", status_code=303)

    session = request.app.state.session_factory()
    try:
        event = _load_event_by_slug(session, slug)
        character = _load_character_by_token(session, token)
    finally:
        session.close()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    if character is None:
        add_flash(request, "error", "That QR code does not match any character.")
        return RedirectResponse(f"/events/{slug}/scan", status_code=303)
    if character.event.slug != slug:
        add_flash(request, "error", "That QR code belongs to a different event.")
        return RedirectResponse(f"/events/{slug}/scan", status_code=303)
    return RedirectResponse(f"/q/{character.qr_token}", status_code=303)


@router.get("/events/{slug}/characters/{character_id}")
async def character_page(request: Request, slug: str, character_id: int):
    current_user = current_user_from_request(request)
    session = request.app.state.session_factory()
    try:
        event = _load_event_by_slug(session, slug)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        character = _find_character(event, character_id)
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        progress_state = None
        note = None
        admin_notes = []
        can_view = is_admin(current_user)
        if current_user and user_in_event(current_user, event):
            user_notes = _notes_for_user(event, current_user)
            progress_state = build_progress_state(list(event.characters), user_notes)
            note = progress_state.note_by_character_id.get(character.id)
            can_view = can_view or can_reveal_character(current_user, character, progress_state)
        if is_admin(current_user):
            user_lookup = {membership.user_id: membership.user for membership in event.memberships}
            admin_notes = []
            for note_item in event.notes:
                if note_item.character_id != character.id or not note_item.note_text.strip():
                    continue
                user = user_lookup.get(note_item.user_id)
                if user is None:
                    user = session.get(User, note_item.user_id)
                if user is None or user.role != "networker":
                    continue
                admin_notes.append(
                    {
                        "user": user,
                        "note_text": note_item.note_text,
                        "updated_at": note_item.updated_at,
                    }
                )
            admin_notes.sort(key=lambda item: (item["user"].display_name.lower(), item["user"].login.lower()))
    finally:
        session.close()

    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="character_detail.html",
        context=template_context(
            request,
            page_title=f"{event.name} character",
            event=event,
            character=character,
            progress_state=progress_state,
            note=note,
            admin_notes=admin_notes,
            can_view=can_view,
            viewer_is_member=user_in_event(current_user, event),
        ),
    )


@router.post("/events/{slug}/characters/{character_id}/notes")
async def save_note(request: Request, slug: str, character_id: int, note_text: str = Form(...)):
    current_user = current_user_from_request(request)
    if current_user is None or current_user.role != "networker":
        add_flash(request, "error", "Log in as a networker account to save notes.")
        return RedirectResponse(f"/events/{slug}/characters/{character_id}", status_code=303)

    cleaned_note = note_text.strip()
    if not cleaned_note:
        add_flash(request, "error", "A note is required to unlock the next character.")
        return RedirectResponse(f"/events/{slug}/characters/{character_id}", status_code=303)

    session = request.app.state.session_factory()
    try:
        event = _load_event_by_slug(session, slug)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        if not user_in_event(current_user, event):
            add_flash(request, "error", "This account is not linked to that event.")
            return RedirectResponse(f"/events/{slug}", status_code=303)
        character = _find_character(event, character_id)
        if character is None:
            raise HTTPException(status_code=404, detail="Character not found.")
        user_notes = _notes_for_user(event, current_user)
        progress_state = build_progress_state(list(event.characters), user_notes)
        if not can_access_character(current_user, character, progress_state):
            add_flash(request, "error", "That character is still locked.")
            return RedirectResponse(f"/events/{slug}", status_code=303)
        if not can_reveal_character(current_user, character, progress_state):
            add_flash(request, "error", "Scan this badge first to open the character.")
            return RedirectResponse(f"/events/{slug}", status_code=303)

        existing_note = session.scalar(
            select(CharacterNote).where(
                CharacterNote.user_id == current_user.id,
                CharacterNote.character_id == character.id,
            )
        )
        if existing_note is None:
            existing_note = CharacterNote(
                user_id=current_user.id,
                event_id=event.id,
                character_id=character.id,
                note_text=cleaned_note,
            )
            session.add(existing_note)
        else:
            existing_note.note_text = cleaned_note
        session.commit()
    finally:
        session.close()

    add_flash(request, "success", "Your notes are saved.")
    return RedirectResponse(f"/events/{slug}/characters/{character_id}", status_code=303)


@router.get("/q/{qr_token}")
async def qr_entry(request: Request, qr_token: str):
    current_user = current_user_from_request(request)
    redirect_target = None
    session = request.app.state.session_factory()
    try:
        character = _load_character_by_token(session, qr_token)
        if (
            character is not None
            and current_user is not None
            and current_user.role == "networker"
            and user_in_event(current_user, character.event)
        ):
            progress_state = build_progress_state(list(character.event.characters), _notes_for_user(character.event, current_user))
            if can_access_character(current_user, character, progress_state):
                _ensure_character_discovery(session, current_user, character.event, character)
        if character is not None:
            redirect_target = f"/events/{character.event.slug}/characters/{character.id}"
    finally:
        session.close()
    if character is None:
        raise HTTPException(status_code=404, detail="QR code not found.")
    return RedirectResponse(redirect_target, status_code=303)


@router.get("/media/{image_key:path}")
async def media_file(request: Request, image_key: str):
    current_user = current_user_from_request(request)
    session = request.app.state.session_factory()
    try:
        statement = (
            select(Character)
            .where(Character.image_key == image_key)
            .options(
                selectinload(Character.event).selectinload(Event.characters),
                selectinload(Character.event).selectinload(Event.memberships).selectinload(EventMembership.user),
                selectinload(Character.event).selectinload(Event.notes),
            )
        )
        character = session.scalar(statement)
        if character is None:
            raise HTTPException(status_code=404, detail="Image not found.")

        can_view = is_admin(current_user)
        if current_user and user_in_event(current_user, character.event):
            user_notes = _notes_for_user(character.event, current_user)
            progress_state = build_progress_state(list(character.event.characters), user_notes)
            can_view = can_view or can_reveal_character(current_user, character, progress_state)
        if not can_view:
            raise HTTPException(status_code=404, detail="Image not found.")

        stored_file = request.app.state.storage.read_bytes(image_key)
    finally:
        session.close()
    return Response(content=stored_file.content, media_type=stored_file.content_type)
