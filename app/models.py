from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="networker")

    memberships: Mapped[list["EventMembership"]] = relationship(
        "EventMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["CharacterNote"]] = relationship(
        "CharacterNote",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)

    memberships: Mapped[list["EventMembership"]] = relationship(
        "EventMembership",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    characters: Mapped[list["Character"]] = relationship(
        "Character",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="Character.position",
    )
    notes: Mapped[list["CharacterNote"]] = relationship(
        "CharacterNote",
        back_populates="event",
        cascade="all, delete-orphan",
    )


class EventMembership(TimestampMixin, Base):
    __tablename__ = "event_memberships"
    __table_args__ = (UniqueConstraint("user_id", "event_id", name="uq_membership_user_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)

    user: Mapped[User] = relationship("User", back_populates="memberships")
    event: Mapped[Event] = relationship("Event", back_populates="memberships")


class Character(TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("event_id", "position", name="uq_character_event_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    real_name: Mapped[str] = mapped_column(String(160), nullable=False)
    fictional_name: Mapped[str] = mapped_column(String(160), nullable=False)
    storyline_truth: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    qr_token: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)

    event: Mapped[Event] = relationship("Event", back_populates="characters")
    notes: Mapped[list["CharacterNote"]] = relationship(
        "CharacterNote",
        back_populates="character",
        cascade="all, delete-orphan",
    )


class CharacterNote(TimestampMixin, Base):
    __tablename__ = "character_notes"
    __table_args__ = (UniqueConstraint("user_id", "character_id", name="uq_note_user_character"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="notes")
    event: Mapped[Event] = relationship("Event", back_populates="notes")
    character: Mapped[Character] = relationship("Character", back_populates="notes")
