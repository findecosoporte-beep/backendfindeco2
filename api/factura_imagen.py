"""Conversión de factura PDF (ticket) a PNG para impresoras térmicas."""

from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image


def pdf_ticket_a_png(pdf_bytes: bytes, *, ticket_format: str = '58') -> bytes:
    """
    Renderiza la primera página del PDF del recibo a PNG monocromo-friendly.

    Ancho objetivo aproximado a 203 dpi:
    - 58 mm → 384 px
    - 80 mm → 576 px
    """
    target_width = 576 if ticket_format == '80' else 384
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        page = doc[0]
        page_w, page_h = page.get_size()
        if page_w <= 0:
            raise ValueError('PDF de factura sin ancho válido.')
        scale = target_width / float(page_w)
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert('RGB')
    finally:
        doc.close()

    # Recorta franja blanca inferior para no desalinear el corte del ticket.
    image = _recortar_espacio_blanco_inferior(image)

    # Escala de grises mejora el dithering en la impresora ESC/POS.
    image = image.convert('L')

    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _recortar_espacio_blanco_inferior(image: Image.Image, umbral: int = 250, margen_blanco: int = 16) -> Image.Image:
    """Elimina filas casi blancas al final del ticket, dejando un pequeño margen."""
    gris = image.convert('L')
    pixels = gris.load()
    width, height = gris.size
    ultima_fila_con_tinta = 0
    for y in range(height - 1, -1, -1):
        if any(pixels[x, y] < umbral for x in range(width)):
            ultima_fila_con_tinta = y
            break
    corte = min(height, ultima_fila_con_tinta + 1 + margen_blanco)
    if corte >= height:
        return image
    return image.crop((0, 0, width, corte))
