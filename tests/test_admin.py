from __future__ import annotations

import csv
import io
from io import StringIO
from zipfile import ZipFile

from sqlalchemy import select

from app.models import Character, CharacterNote
from app.utils import encode_payload
from tests.conftest import create_character, create_event, create_note, create_user, link_user_to_event, login


def test_event_import_validation_rejects_existing_and_duplicate_rows(app, client):
    admin = create_user(app, "admin", "admin-pass", role="admin")
    create_event(app, "Existing Event", "existing-event")
    login(client, admin.login, "admin-pass")

    csv_payload = "event_name\nExisting Event\nFresh Event\nFresh Event\n"
    response = client.post(
        "/admin/events/import/validate",
        files={"csv_file": ("events.csv", csv_payload, "text/csv")},
    )

    assert response.status_code == 200
    assert "already exists" in response.text
    assert "duplicate event_name" in response.text


def test_badge_zip_download_contains_one_pdf_per_character(app, client):
    admin = create_user(app, "admin", "admin-pass", role="admin")
    event = create_event(app, "Badge Night", "badge-night")
    create_character(app, event.id, 1, "Alpha Badge", real_name="Alpha Real")
    create_character(app, event.id, 2, "Beta Badge")
    login(client, admin.login, "admin-pass")

    response = client.get(f"/admin/events/{event.id}/characters/badges.zip")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    archive = ZipFile(io.BytesIO(response.content))
    names = sorted(archive.namelist())
    assert names == ["01-alpha-badge.pdf", "02-beta-badge.pdf"]

    first_badge = archive.read("01-alpha-badge.pdf")
    assert b"Badge Night" in first_badge
    assert b"Alpha Badge" in first_badge
    assert b"Alpha Real" not in first_badge
    assert b"Real name" not in first_badge
    assert b"Level 1" not in first_badge
    assert b"Special Guest Badge" not in first_badge
    assert b"http://testserver/q/" not in first_badge


def test_admin_character_page_shows_networker_notes(app, client):
    admin = create_user(app, "admin", "admin-pass", role="admin", display_name="Admin")
    first_networker = create_user(app, "jane", "pass-one", display_name="Jane")
    second_networker = create_user(app, "nick", "pass-two", display_name="Nick")
    event = create_event(app, "Note Summit", "note-summit")
    character = create_character(app, event.id, 1, "Closer")
    link_user_to_event(app, first_networker.id, event.id)
    link_user_to_event(app, second_networker.id, event.id)
    create_note(app, first_networker.id, event.id, character.id, "Asked about the closing dinner.")
    create_note(app, second_networker.id, event.id, character.id, "Works in finance and loves sailing.")

    login(client, admin.login, "admin-pass")
    response = client.get(f"/events/{event.slug}/characters/{character.id}")

    assert response.status_code == 200
    assert "Notes" in response.text
    assert "Networker notes" not in response.text
    assert "Jane" in response.text
    assert "Nick" in response.text
    assert "Asked about the closing dinner." in response.text
    assert "Works in finance and loves sailing." in response.text
    assert "Admins can inspect the character" not in response.text


def test_character_export_includes_note_columns_and_import_ignores_them(app, client):
    admin = create_user(app, "admin", "admin-pass", role="admin")
    networker = create_user(app, "jane", "note-pass", display_name="Jane")
    event = create_event(app, "Export Notes", "export-notes")
    character = create_character(app, event.id, 1, "Closer", real_name="Real Closer")
    link_user_to_event(app, networker.id, event.id)
    create_note(app, networker.id, event.id, character.id, "Original note that should stay untouched.")

    login(client, admin.login, "admin-pass")
    export_response = client.get(f"/admin/events/{event.id}/characters/export")
    assert export_response.status_code == 200

    reader = csv.DictReader(StringIO(export_response.text))
    rows = list(reader)
    assert "note__jane" in reader.fieldnames
    assert rows[0]["note__jane"] == "Original note that should stay untouched."

    import_payload = (
        "event_name,position,real_name,fictional_name,storyline_truth,note__jane\n"
        "Export Notes,1,Real Closer,Updated Fiction,Updated truth,This should be ignored\n"
    )
    validate_response = client.post(
        f"/admin/events/{event.id}/characters/import/validate",
        files={"csv_file": ("characters.csv", import_payload, "text/csv")},
    )
    assert validate_response.status_code == 200
    assert "Ready to import" in validate_response.text

    commit_response = client.post(
        f"/admin/events/{event.id}/characters/import/commit",
        data={"import_payload": encode_payload(import_payload)},
        follow_redirects=True,
    )
    assert commit_response.status_code == 200
    assert "Imported 1 character row" in commit_response.text

    session = app.state.session_factory()
    try:
        updated_character = session.get(Character, character.id)
        updated_note = session.scalar(
            select(CharacterNote).where(
                CharacterNote.user_id == networker.id,
                CharacterNote.character_id == character.id,
            )
        )
    finally:
        session.close()

    assert updated_character.fictional_name == "Updated Fiction"
    assert updated_character.storyline_truth == "Updated truth"
    assert updated_note is not None
    assert updated_note.note_text == "Original note that should stay untouched."
