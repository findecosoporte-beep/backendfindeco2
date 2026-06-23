"""Utilidades para interpretar cuotas en textos de documentos de pago."""

import re


def extract_cuota_numero_from_documento(documento: str | None) -> int | None:
    """Extrae el número de cuota de textos como «Cuota 3» (insensible a mayúsculas)."""
    match = re.search(r'cuota\s*(\d+)', (documento or '').strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))
