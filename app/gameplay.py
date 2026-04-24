from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.auth import is_admin
from app.models import Character, CharacterNote, Event, User


@dataclass
class CharacterProgressState:
    completed_count: int
    unlocked_position: int
    note_by_character_id: dict[int, CharacterNote]
    discovered_character_ids: set[int]
    accessible_character_ids: set[int]


@dataclass
class LeaderboardEntry:
    user: User
    completed_count: int
    completed_at: Optional[datetime]


def build_progress_state(characters: list[Character], notes: list[CharacterNote]) -> CharacterProgressState:
    discovered_character_ids = {note.character_id for note in notes}
    note_by_character_id = {note.character_id: note for note in notes if note.note_text.strip()}
    completed_count = 0
    for character in characters:
        note = note_by_character_id.get(character.id)
        if note is None:
            break
        completed_count += 1
    total_characters = len(characters)
    unlocked_position = 0
    if total_characters:
        unlocked_position = min(completed_count + 1, total_characters)
    accessible_character_ids = {
        character.id
        for character in characters
        if character.position <= unlocked_position or character.position <= completed_count
    }
    return CharacterProgressState(
        completed_count=completed_count,
        unlocked_position=unlocked_position,
        note_by_character_id=note_by_character_id,
        discovered_character_ids=discovered_character_ids,
        accessible_character_ids=accessible_character_ids,
    )


def can_access_character(user: Optional[User], character: Character, progress_state: CharacterProgressState) -> bool:
    if is_admin(user):
        return True
    if user is None:
        return False
    return character.id in progress_state.accessible_character_ids


def can_reveal_character(user: Optional[User], character: Character, progress_state: CharacterProgressState) -> bool:
    if is_admin(user):
        return True
    if user is None:
        return False
    return (
        character.id in progress_state.accessible_character_ids
        and character.id in progress_state.discovered_character_ids
    )


def leaderboard_for_event(event: Event) -> list[LeaderboardEntry]:
    ordered_characters = list(event.characters)
    members = [membership.user for membership in event.memberships if membership.user.role == "networker"]
    entries: list[LeaderboardEntry] = []
    for user in members:
        user_notes = [note for note in event.notes if note.user_id == user.id and note.note_text.strip()]
        progress_state = build_progress_state(ordered_characters, user_notes)
        completed_at = None
        if progress_state.completed_count:
            last_completed_character = ordered_characters[progress_state.completed_count - 1]
            completed_at = progress_state.note_by_character_id[last_completed_character.id].updated_at
        entries.append(
            LeaderboardEntry(
                user=user,
                completed_count=progress_state.completed_count,
                completed_at=completed_at,
            )
        )
    entries.sort(
        key=lambda item: (
            -item.completed_count,
            item.completed_at or datetime.max,
            item.user.display_name.lower(),
        )
    )
    return entries


def user_in_event(user: Optional[User], event: Event) -> bool:
    if user is None:
        return False
    if is_admin(user):
        return True
    return any(membership.user_id == user.id for membership in event.memberships)
