"""Consecutivo compartido para codigo_prestamo y numero_prestamo (formato PR-0001)."""

from __future__ import annotations

import re

from django.db.models import QuerySet

from api.models import Prestamo

PREFIJO = 'PR-'
ANCHO = 4
MAX_VALOR = 9999
_REGEX_DIGITOS_FINAL = re.compile(r'^(.*?)(\d+)$')


def _secuencia_desde_texto(texto: str | None) -> int | None:
    """Extrae el sufijo numérico (PR-0001 → 1, 042 → 42). Ignora timestamps enormes."""
    valor = (texto or '').strip()
    if not valor:
        return None
    coincidencia = _REGEX_DIGITOS_FINAL.match(valor)
    if not coincidencia:
        return None
    seq = int(coincidencia.group(2))
    if seq <= 0 or seq > MAX_VALOR:
        return None
    return seq


def max_secuencia_prestamos(qs: QuerySet[Prestamo] | None = None) -> int:
    if qs is None:
        qs = Prestamo.objects.all()
    max_seq = 0
    for campo in ('codigo_prestamo', 'numero_prestamo'):
        for valor in qs.values_list(campo, flat=True).iterator(chunk_size=500):
            seq = _secuencia_desde_texto(valor)
            if seq is not None and seq > max_seq:
                max_seq = seq
    return max_seq


def formatear_consecutivo(seq: int) -> str:
    return f'{PREFIJO}{str(seq).zfill(ANCHO)}'


def siguiente_numeracion_prestamo(qs: QuerySet[Prestamo] | None = None) -> str:
    return formatear_consecutivo(max_secuencia_prestamos(qs) + 1)


def numeracion_prestamo_response(qs: QuerySet[Prestamo] | None = None) -> dict[str, str]:
    valor = siguiente_numeracion_prestamo(qs)
    return {
        'codigo_prestamo': valor,
        'numero_prestamo': valor,
    }
