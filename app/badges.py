from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZipFile

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import Character


def build_qr_png(data: str) -> bytes:
    image = qrcode.make(data)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_badge_pdf(character: Character, qr_url: str) -> bytes:
    qr_png = build_qr_png(qr_url)
    buffer = io.BytesIO()
    badge = canvas.Canvas(buffer, pagesize=landscape(A6))
    width, height = landscape(A6)

    badge.setFillColor(colors.HexColor("#0f2f3a"))
    badge.rect(0, 0, width, height, fill=1, stroke=0)
    badge.setFillColor(colors.HexColor("#efe8d8"))
    badge.roundRect(8 * mm, 8 * mm, width - 16 * mm, height - 16 * mm, 8 * mm, fill=1, stroke=0)

    badge.setFillColor(colors.HexColor("#d97706"))
    badge.setFont("Helvetica-Bold", 10)
    badge.drawString(16 * mm, height - 18 * mm, "NETWORK KING")

    badge.setFillColor(colors.HexColor("#17313a"))
    badge.setFont("Helvetica", 7)
    badge.drawString(16 * mm, height - 24 * mm, "Special Guest Badge")

    badge.setFont("Helvetica-Bold", 18)
    badge.drawString(16 * mm, height - 38 * mm, character.fictional_name[:28])

    badge.setFont("Helvetica", 8)
    badge.drawString(16 * mm, height - 46 * mm, f"Real name: {character.real_name[:36]}")
    badge.drawString(16 * mm, height - 52 * mm, f"Level {character.position}")

    image_buffer = ImageReader(io.BytesIO(qr_png))
    badge.drawImage(image_buffer, width - 52 * mm, 16 * mm, 36 * mm, 36 * mm)

    badge.setFont("Helvetica", 6)
    badge.setFillColor(colors.HexColor("#52636a"))
    badge.drawString(16 * mm, 14 * mm, qr_url)

    badge.showPage()
    badge.save()
    return buffer.getvalue()


def build_badge_zip(characters: list[Character], app_base_url: str) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for character in characters:
            badge_pdf = build_badge_pdf(character, f"{app_base_url}/q/{character.qr_token}")
            safe_name = character.fictional_name.lower().replace(" ", "-")
            archive.writestr(f"{character.position:02d}-{safe_name}.pdf", badge_pdf)
    return buffer.getvalue()
