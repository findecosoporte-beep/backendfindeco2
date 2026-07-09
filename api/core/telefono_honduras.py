"""Normalización de teléfonos celulares de Honduras (+504, 8 dígitos locales)."""

from __future__ import annotations

import re

PREFIJO_TELEFONO_HN = '504'
TELEFONO_HN_DIGITOS = 8


def normalizar_telefono_hn(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r'\D', '', str(value).strip())
    if digits.startswith(PREFIJO_TELEFONO_HN):
        digits = digits[len(PREFIJO_TELEFONO_HN) :]
    if not digits:
        return None
    if len(digits) != TELEFONO_HN_DIGITOS:
        raise ValueError(
            f'El teléfono debe tener {TELEFONO_HN_DIGITOS} dígitos (Honduras +{PREFIJO_TELEFONO_HN}).',
        )
    return digits


def normalizar_telefono_hn_opcional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return normalizar_telefono_hn(text)
