from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.models import Character


APP_DIR = Path(__file__).resolve().parent
BADGE_LOGO_PATH = APP_DIR / "static" / "apple-touch-icon.png"


def build_qr_png(data: str) -> bytes:
    image = qrcode.make(data)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fit_lines(text: str, font_name: str, font_size: float, max_width: float, max_lines: int) -> list[str]:
    lines = simpleSplit(text, font_name, font_size, max_width) or [text]
    if len(lines) <= max_lines:
        return lines
    trimmed = lines[:max_lines]
    last_line = trimmed[-1].rstrip()
    while last_line and stringWidth(f"{last_line}...", font_name, font_size) > max_width:
        last_line = last_line[:-1].rstrip()
    trimmed[-1] = f"{last_line}..." if last_line else "..."
    return trimmed


def build_badge_pdf(character: Character, event_name: str, qr_url: str) -> bytes:
    qr_png = build_qr_png(qr_url)
    buffer = io.BytesIO()
    badge = canvas.Canvas(buffer, pagesize=landscape(A6), pageCompression=0)
    width, height = landscape(A6)
    panel_x = 5.5 * mm
    panel_y = 5.5 * mm
    panel_width = width - (11 * mm)
    panel_height = height - (11 * mm)
    qr_size = 48 * mm
    qr_frame_size = qr_size + (8 * mm)
    qr_x = panel_x + panel_width - qr_frame_size - (6 * mm)
    qr_y = panel_y + ((panel_height - qr_frame_size) / 2)
    text_x = panel_x + (10 * mm)
    text_width = qr_x - text_x - (8 * mm)
    content_top = panel_y + panel_height - (8 * mm)

    badge.setFillColor(colors.HexColor("#0f2f3a"))
    badge.rect(0, 0, width, height, fill=1, stroke=0)
    badge.setFillColor(colors.HexColor("#efe8d8"))
    badge.roundRect(panel_x, panel_y, panel_width, panel_height, 8 * mm, fill=1, stroke=0)
    badge.setFillColor(colors.HexColor("#d97706"))
    badge.roundRect(panel_x + (6 * mm), panel_y + (8 * mm), 2.5 * mm, panel_height - (16 * mm), 1.2 * mm, fill=1, stroke=0)

    badge.setFillColor(colors.HexColor("#fffaf0"))
    badge.roundRect(qr_x, qr_y, qr_frame_size, qr_frame_size, 5 * mm, fill=1, stroke=0)

    if BADGE_LOGO_PATH.exists():
        logo_size = 15 * mm
        logo_y = content_top - logo_size
        badge.drawImage(
            ImageReader(str(BADGE_LOGO_PATH)),
            text_x,
            logo_y,
            logo_size,
            logo_size,
            mask="auto",
        )
    else:
        logo_size = 0
        logo_y = content_top

    badge.setFillColor(colors.HexColor("#17313a"))
    event_lines = _fit_lines(event_name, "Helvetica-Bold", 11.5, text_width, max_lines=2)
    event_top = logo_y - (5 * mm)
    badge.setFont("Helvetica-Bold", 11.5)
    for index, line in enumerate(event_lines):
        badge.drawString(text_x, event_top - (index * 5.4 * mm), line)

    name_lines = _fit_lines(character.fictional_name, "Helvetica-Bold", 21, text_width, max_lines=3)
    name_top = event_top - (len(event_lines) * 5.4 * mm) - (8 * mm)
    badge.setFont("Helvetica-Bold", 21)
    for index, line in enumerate(name_lines):
        badge.drawString(text_x, name_top - (index * 8.2 * mm), line)

    image_buffer = ImageReader(io.BytesIO(qr_png))
    badge.drawImage(
        image_buffer,
        qr_x + (4 * mm),
        qr_y + (4 * mm),
        qr_size,
        qr_size,
        mask="auto",
    )

    badge.showPage()
    badge.save()
    return buffer.getvalue()


def build_badge_zip(characters: list[Character], app_base_url: str, event_name: str) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for character in characters:
            badge_pdf = build_badge_pdf(character, event_name, f"{app_base_url}/q/{character.qr_token}")
            safe_name = character.fictional_name.lower().replace(" ", "-")
            archive.writestr(f"{character.position:02d}-{safe_name}.pdf", badge_pdf)
    return buffer.getvalue()
