from __future__ import annotations

from app.auth import verify_password
from app.utils import encode_payload
from tests.conftest import create_character, create_event, create_user, fetch_user, fetch_user_with_memberships, link_user_to_event, login


def test_networker_progression_unlocks_next_character(app, client):
    user = create_user(app, "nick", "secret-pass", display_name="Nick")
    event = create_event(app, "Bachelor Bash", "bachelor-bash")
    first = create_character(app, event.id, 1, "Captain Card")
    second = create_character(app, event.id, 2, "Deal Maker")
    create_character(app, event.id, 3, "Silent Closer")
    link_user_to_event(app, user.id, event.id)

    response = login(client, "nick", "secret-pass")
    assert response.status_code == 200

    response = client.get(f"/events/{event.slug}")
    body = response.text
    assert "Captain Card" in body
    assert "Deal Maker" not in body

    response = client.post(
        f"/events/{event.slug}/characters/{first.id}/notes",
        data={"note_text": "Strong opening story"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    response = client.get(f"/events/{event.slug}")
    body = response.text
    assert "Captain Card" in body
    assert "Deal Maker" in body
    assert "Silent Closer" not in body

    response = client.post(
        f"/events/{event.slug}/characters/{second.id}/notes",
        data={"note_text": "Brought up a huge deal"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Your notes are saved." in response.text

    response = client.get(f"/events/{event.slug}")
    assert "Silent Closer" in response.text


def test_public_and_unlinked_networker_only_see_locked_character(app, client):
    event = create_event(app, "Locked Summit", "locked-summit")
    first = create_character(app, event.id, 1, "Visible Only Later", qr_token="summit-token")
    outsider = create_user(app, "outsider", "still-out")

    public_response = client.get(f"/q/{first.qr_token}", follow_redirects=True)
    assert public_response.status_code == 200
    assert "still locked" in public_response.text.lower()
    assert "Visible Only Later" not in public_response.text

    login(client, "outsider", "still-out")
    outsider_response = client.get(f"/q/{first.qr_token}", follow_redirects=True)
    assert outsider_response.status_code == 200
    assert "still locked" in outsider_response.text.lower()
    assert "Visible Only Later" not in outsider_response.text


def test_admin_routes_require_admin_role(app, client):
    create_user(app, "host", "top-secret", role="admin", display_name="Host")
    create_user(app, "guest", "guess-me")

    response = client.get("/admin/events", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    login(client, "guest", "guess-me")
    response = client.get("/admin/events", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    client.get("/logout", follow_redirects=True)
    login(client, "host", "top-secret")
    response = client.get("/admin/events")
    assert response.status_code == 200
    assert "Manage network events" in response.text


def test_networker_import_updates_links_without_resetting_password_when_blank(app, client):
    admin = create_user(app, "admin", "admin-pass", role="admin", display_name="Admin")
    first_event = create_event(app, "Morning Mixer", "morning-mixer")
    second_event = create_event(app, "Evening Gala", "evening-gala")
    networker = create_user(app, "jane", "original-pass", display_name="Jane")
    link_user_to_event(app, networker.id, first_event.id)

    login(client, admin.login, "admin-pass")
    csv_payload = "login,name,password,event_names\njane,Jane Updated,,Evening Gala\n"

    validate_response = client.post(
        "/admin/networkers/import/validate",
        files={"csv_file": ("networkers.csv", csv_payload, "text/csv")},
    )
    assert validate_response.status_code == 200
    assert "Ready to import" in validate_response.text

    commit_response = client.post(
        "/admin/networkers/import/commit",
        data={"import_payload": encode_payload(csv_payload)},
        follow_redirects=True,
    )
    assert commit_response.status_code == 200
    assert "Imported 1 networker row" in commit_response.text

    updated_user = fetch_user(app, "jane")
    assert updated_user.display_name == "Jane Updated"
    assert verify_password("original-pass", updated_user.password_hash)

    updated_user_with_memberships = fetch_user_with_memberships(app, "jane")
    membership_event_ids = sorted(membership.event_id for membership in updated_user_with_memberships.memberships)
    assert membership_event_ids == [second_event.id]
