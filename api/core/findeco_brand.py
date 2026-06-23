"""Logo y utilidades de marca FINDECO para PDFs."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image

_LOGO_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'findeco-logo.png'


def ruta_logo_findeco() -> Path | None:
    if _LOGO_PATH.is_file():
        return _LOGO_PATH
    return None


def platypus_logo_findeco(ancho_mm: float = 48, alto_mm: float = 18) -> Image | None:
    """Imagen centrada para documentos Platypus (historial, reportes)."""
    path = ruta_logo_findeco()
    if path is None:
        return None
    img = Image(str(path), width=ancho_mm * mm, height=alto_mm * mm)
    img.hAlign = 'CENTER'
    return img


def dibujar_logo_ticket(
    pdf,
    center_x: float,
    y_top: float,
    max_width: float,
    max_height_mm: float,
) -> float:
    """
    Dibuja el logo centrado en un ticket (canvas).
    Retorna la coordenada Y debajo del logo para seguir escribiendo.
    """
    path = ruta_logo_findeco()
    if path is None:
        return y_top

    reader = ImageReader(str(path))
    iw, ih = reader.getSize()
    if iw <= 0 or ih <= 0:
        return y_top

    max_h = max_height_mm * mm
    scale = min(max_width / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    x = center_x - (w / 2)
    y_bottom = y_top - h
    pdf.drawImage(reader, x, y_bottom, width=w, height=h, preserveAspectRatio=True, mask='auto')
    return y_bottom - (2 * mm)
