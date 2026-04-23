from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import hash_password
from app.main import create_app
from app.models import Character, CharacterNote, Event, EventMembership, User
from app.settings import Settings


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    return Settings(
        secret_key="test-secret-key",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        app_base_url="http://testserver",
        local_media_root=tmp_path / "uploads",
        seed_admin_login="",
        seed_admin_password="",
    )


@pytest.fixture
def app(app_settings: Settings):
    return create_app(app_settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def create_user(app, login: str, password: str, role: str = "networker", display_name: Optional[str] = None) -> User:
    session = app.state.session_factory()
    try:
        user = User(
            login=login,
            display_name=display_name or login.title(),
            password_hash=hash_password(password),
            role=role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def create_event(app, name: str, slug: str) -> Event:
    session = app.state.session_factory()
    try:
        event = Event(name=name, slug=slug)
        session.add(event)
        session.commit()
        session.refresh(event)
        return event
    finally:
        session.close()


def link_user_to_event(app, user_id: int, event_id: int) -> None:
    session = app.state.session_factory()
    try:
        session.add(EventMembership(user_id=user_id, event_id=event_id))
        session.commit()
    finally:
        session.close()


def create_character(
    app,
    event_id: int,
    position: int,
    fictional_name: str,
    real_name: Optional[str] = None,
    qr_token: Optional[str] = None,
) -> Character:
    session = app.state.session_factory()
    try:
        character = Character(
            event_id=event_id,
            position=position,
            fictional_name=fictional_name,
            real_name=real_name or fictional_name,
            storyline_truth=f"Truth for {fictional_name}",
            qr_token=qr_token or f"token-{event_id}-{position}",
        )
        session.add(character)
        session.commit()
        session.refresh(character)
        return character
    finally:
        session.close()


def create_note(app, user_id: int, event_id: int, character_id: int, note_text: str) -> CharacterNote:
    session = app.state.session_factory()
    try:
        note = CharacterNote(
            user_id=user_id,
            event_id=event_id,
            character_id=character_id,
            note_text=note_text,
        )
        session.add(note)
        session.commit()
        session.refresh(note)
        return note
    finally:
        session.close()


def fetch_user(app, login: str) -> User:
    session = app.state.session_factory()
    try:
        return session.scalar(select(User).where(User.login == login))
    finally:
        session.close()


def fetch_user_with_memberships(app, login: str) -> User:
    session = app.state.session_factory()
    try:
        statement = (
            select(User)
            .where(User.login == login)
            .options(selectinload(User.memberships))
        )
        return session.scalar(statement)
    finally:
        session.close()


def login(client: TestClient, login_value: str, password: str):
    return client.post(
        "/login",
        data={"login": login_value, "password": password},
        follow_redirects=True,
    )
