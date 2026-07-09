"""Movimientos de cobro desglosados desde pagos (cuota vs abono a capital)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .cuotas import extract_cuota_numero_from_documento
from .money import round_money

__all__ = [
    'abonado_por_cuota_desde_movimientos',
    'abonado_por_cuota_desde_pagos',
    'abonos_capital_desde_pagos',
    'cuota_pago_desde_movimientos',
    'movimientos_desde_pago',
    'pago_tiene_varios_movimientos',
]


def _monto_linea(item: dict) -> Decimal:
    if 'total' in item and item['total'] is not None:
        return round_money(Decimal(str(item['total'])))
    capital = Decimal(str(item.get('capital', '0')))
    interes = Decimal(str(item.get('interes', '0')))
    mora = Decimal(str(item.get('mora', '0')))
    return round_money(capital + interes + mora)


def movimientos_desde_pago(pago) -> list[dict]:
    """
    Expande un registro Pago en movimientos tipados.

    - ``cuota``: líneas del plan de cuotas (incluye parciales).
    - ``abono_capital``: excedente aplicado a capital fuera del plan por cuota.
    """
    detalle = getattr(pago, 'detalle_distribucion', None) or []
    base = {
        'id_pago': pago.id_pago,
        'fecha_pago': pago.fecha_pago.isoformat() if pago.fecha_pago else None,
        'cobrado_en': (
            pago.cobrado_en.isoformat()
            if getattr(pago, 'cobrado_en', None) is not None
            else None
        ),
        'numero_factura': getattr(pago, 'numero_factura', None),
    }
    movimientos: list[dict] = []

    if detalle:
        for item in detalle:
            if not isinstance(item, dict):
                continue
            mov = {**base, **item}
            if item.get('abono_capital'):
                mov['tipo'] = 'abono_capital'
            elif item.get('cuota') is not None:
                mov['tipo'] = 'cuota'
            else:
                continue
            mov['total'] = str(_monto_linea(item))
            movimientos.append(mov)
        if movimientos:
            return movimientos

    numero = extract_cuota_numero_from_documento(getattr(pago, 'documento', None))
    capital = round_money(Decimal(pago.capital))
    interes = round_money(Decimal(pago.interes))
    mora = round_money(Decimal(pago.mora))
    total = round_money(capital + interes + mora)
    if numero is not None:
        return [
            {
                **base,
                'tipo': 'cuota',
                'cuota': numero,
                'capital': str(capital),
                'interes': str(interes),
                'mora': str(mora),
                'total': str(total),
                'documento': pago.documento or f'Cuota {numero}',
            }
        ]
    if capital > 0 and interes == 0 and mora == 0:
        return [
            {
                **base,
                'tipo': 'abono_capital',
                'abono_capital': True,
                'capital': str(capital),
                'interes': '0.00',
                'mora': '0.00',
                'total': str(total),
                'documento': pago.documento or 'Abono a capital',
            }
        ]
    if numero is None and total > 0:
        doc = (pago.documento or '').lower()
        if 'abono' in doc and 'capital' in doc:
            return [
                {
                    **base,
                    'tipo': 'abono_capital',
                    'abono_capital': True,
                    'capital': str(capital),
                    'interes': str(interes),
                    'mora': str(mora),
                    'total': str(total),
                    'documento': pago.documento or 'Abono a capital',
                }
            ]
    return movimientos


def pago_tiene_varios_movimientos(pago) -> bool:
    return len(movimientos_desde_pago(pago)) > 1


def abonado_por_cuota_desde_movimientos(pagos) -> dict[int, Decimal]:
    abonado: dict[int, Decimal] = defaultdict(lambda: Decimal('0.00'))
    for pago in pagos:
        for mov in movimientos_desde_pago(pago):
            if mov.get('tipo') != 'cuota':
                continue
            cuota = mov.get('cuota')
            if cuota is None:
                continue
            abonado[int(cuota)] += _monto_linea(mov)
    return dict(abonado)


def abonado_por_cuota_desde_pagos(pagos) -> dict[int, Decimal]:
    """Suma abonado por cuota usando detalle_distribucion cuando existe."""
    return abonado_por_cuota_desde_movimientos(pagos)


def abonos_capital_desde_pagos(pagos) -> list[dict]:
    filas: list[dict] = []
    for pago in pagos:
        for mov in movimientos_desde_pago(pago):
            if mov.get('tipo') == 'abono_capital':
                filas.append(mov)
    filas.sort(key=lambda row: (row.get('fecha_pago') or '', row.get('id_pago') or 0))
    return filas


def cuota_pago_desde_movimientos(pagos) -> dict[int, dict]:
    """Mejor referencia de pago/factura por número de cuota."""
    mapa: dict[int, dict] = {}
    for pago in pagos:
        for mov in movimientos_desde_pago(pago):
            if mov.get('tipo') != 'cuota':
                continue
            cuota = mov.get('cuota')
            if cuota is None:
                continue
            numero = int(cuota)
            if numero not in mapa:
                mapa[numero] = {
                    'id_pago': pago.id_pago,
                    'fecha_pago': mov.get('fecha_pago'),
                    'cobrado_en': mov.get('cobrado_en'),
                    'documento': f'Cuota {numero}',
                    'monto_movimiento': mov.get('total'),
                    'parcial': bool(mov.get('parcial')),
                }
    return mapa
