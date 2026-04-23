from __future__ import annotations

import io
from zipfile import ZipFile

from tests.conftest import create_character, create_event, create_user, login


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
    create_character(app, event.id, 1, "Alpha Badge")
    create_character(app, event.id, 2, "Beta Badge")
    login(client, admin.login, "admin-pass")

    response = client.get(f"/admin/events/{event.id}/characters/badges.zip")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    archive = ZipFile(io.BytesIO(response.content))
    names = sorted(archive.namelist())
    assert names == ["01-alpha-badge.pdf", "02-beta-badge.pdf"]
