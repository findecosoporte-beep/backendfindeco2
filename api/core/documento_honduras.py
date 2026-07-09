"""Normalización de DNI (identidad) y RTN de Honduras."""

from __future__ import annotations

import re

DNI_HN_DIGITOS = 13
RTN_HN_DIGITOS = 14


def _solo_digitos(value: str) -> str:
    return re.sub(r'\D', '', value.strip())


def formatear_dni_hn(digits: str) -> str:
    if len(digits) <= 4:
        return digits
    if len(digits) <= 8:
        return f'{digits[:4]}-{digits[4:]}'
    return f'{digits[:4]}-{digits[4:8]}-{digits[8:]}'


def normalizar_dni_hn(value: str | None) -> str:
    if value is None:
        raise ValueError('El DNI es obligatorio.')
    digits = _solo_digitos(str(value))
    if len(digits) != DNI_HN_DIGITOS:
        raise ValueError(
            f'El DNI debe tener {DNI_HN_DIGITOS} dígitos (formato XXXX-XXXX-XXXXX).',
        )
    return formatear_dni_hn(digits)


def normalizar_rtn_hn(value: str | None) -> str:
    digits = _solo_digitos(str(value or ''))
    if len(digits) != RTN_HN_DIGITOS:
        raise ValueError(f'El RTN debe tener {RTN_HN_DIGITOS} dígitos.')
    return digits


def normalizar_rtn_hn_opcional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return normalizar_rtn_hn(text)
