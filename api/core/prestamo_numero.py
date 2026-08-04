"""Consecutivo compacto compartido para codigo_prestamo y numero_prestamo."""

from __future__ import annotations

import re

from django.db.models import QuerySet

from api.models import Prestamo

ANCHO_COMPACTO = 3
MAX_DIGITOS = 4
MAX_VALOR = 9999
_REGEX_COMPACTO = re.compile(r'^\d{1,4}$')


def _secuencia_compacta(texto: str | None) -> int | None:
    """Solo cuenta códigos cortos puros (001, 12, 999). Ignora PR-… o timestamps."""
    valor = (texto or '').strip()
    if not _REGEX_COMPACTO.match(valor):
        return None
    seq = int(valor)
    if seq <= 0 or seq > MAX_VALOR:
        return None
    return seq


def max_secuencia_prestamos(qs: QuerySet[Prestamo] | None = None) -> int:
    if qs is None:
        qs = Prestamo.objects.all()
    max_seq = 0
    for campo in ('codigo_prestamo', 'numero_prestamo'):
        for valor in qs.values_list(campo, flat=True).iterator(chunk_size=500):
            seq = _secuencia_compacta(valor)
            if seq is not None and seq > max_seq:
                max_seq = seq
    return max_seq


def formatear_consecutivo(seq: int) -> str:
    """001–999 con ceros; a partir de 1000 sin relleno (evita números enormes)."""
    if seq < 1000:
        return str(seq).zfill(ANCHO_COMPACTO)
    return str(seq)


def siguiente_numeracion_prestamo(qs: QuerySet[Prestamo] | None = None) -> str:
    return formatear_consecutivo(max_secuencia_prestamos(qs) + 1)


def numeracion_prestamo_response(qs: QuerySet[Prestamo] | None = None) -> dict[str, str]:
    valor = siguiente_numeracion_prestamo(qs)
    return {
        'codigo_prestamo': valor,
        'numero_prestamo': valor,
    }
