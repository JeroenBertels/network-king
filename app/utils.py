from __future__ import annotations

import base64
import csv
import io
import re
import secrets
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse


SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    cleaned = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return cleaned or "event"


def new_qr_token() -> str:
    return secrets.token_urlsafe(18)


def encode_payload(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_payload(value: str) -> str:
    return base64.b64decode(value.encode("ascii")).decode("utf-8")


def parse_csv_text(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return [{key.strip(): (value or "").strip() for key, value in row.items()} for row in reader]


def dump_csv(rows: Iterable[dict[str, str]], fieldnames: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def parse_event_names(value: str) -> list[str]:
    chunks = re.split(r"\s*\|\s*|\s*;\s*", value.strip()) if value.strip() else []
    return [chunk for chunk in chunks if chunk]


def format_event_names(names: list[str]) -> str:
    return " | ".join(names)


def extract_qr_token(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        path = urlparse(value).path.rstrip("/")
        if path.startswith("/q/"):
            return path.split("/q/", 1)[1]
    if value.startswith("/q/"):
        return value.split("/q/", 1)[1]
    return value


@dataclass
class FlashMessage:
    level: str
    text: str


FLASH_SESSION_KEY = "_flash_messages"


def add_flash(request, level: str, text: str) -> None:
    messages = request.session.setdefault(FLASH_SESSION_KEY, [])
    messages.append({"level": level, "text": text})


def pop_flashes(request) -> list[FlashMessage]:
    messages = request.session.pop(FLASH_SESSION_KEY, [])
    return [FlashMessage(level=item["level"], text=item["text"]) for item in messages]

