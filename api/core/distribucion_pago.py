"""Distribución de cobros: abonos parciales quedan en la misma cuota sin interés adicional."""

from collections import defaultdict
from decimal import Decimal

from .cuotas import extract_cuota_numero_from_documento
from .money import round_money
from .reporte_saldos import monto_cuota_programada

CUOTA_PAGADA_TOLERANCIA = Decimal('0.01')

__all__ = [
    'CUOTA_PAGADA_TOLERANCIA',
    'abonado_por_cuota_desde_pagos',
    'cuota_esta_pagada',
    'cuotas_pagadas_completas',
    'distribuir_monto_en_cuotas',
    'pendiente_cuota',
    'saldo_pendiente_con_abonos',
    'saldo_pendiente_tras_abono',
]


def abonado_por_cuota_desde_pagos(pagos) -> dict[int, Decimal]:
    """Suma capital+interés+mora abonado por número de cuota."""
    abonado: dict[int, Decimal] = defaultdict(lambda: Decimal('0.00'))
    for pg in pagos:
        numero = extract_cuota_numero_from_documento(pg.documento)
        if numero is None:
            continue
        abonado[numero] += Decimal(pg.capital) + Decimal(pg.interes) + Decimal(pg.mora)
    return dict(abonado)


def cuota_esta_pagada(abonado: Decimal, total_programado: Decimal) -> bool:
    return abonado >= total_programado - CUOTA_PAGADA_TOLERANCIA


def pendiente_cuota(cuota, abonado: Decimal) -> Decimal:
    total = monto_cuota_programada(cuota)
    resto = total - abonado
    if resto <= CUOTA_PAGADA_TOLERANCIA:
        return Decimal('0.00')
    return round_money(resto)


def cuotas_pagadas_completas(plan_rows: list, abonado_por_cuota: dict[int, Decimal]) -> set[int]:
    pagadas: set[int] = set()
    for row in plan_rows:
        if cuota_esta_pagada(
            abonado_por_cuota.get(row.numero_cuota, Decimal('0.00')),
            monto_cuota_programada(row),
        ):
            pagadas.add(row.numero_cuota)
    return pagadas


def saldo_pendiente_con_abonos(plan_rows: list, abonado_por_cuota: dict[int, Decimal]) -> Decimal:
    """Capital + intereses aún pendientes, descontando abonos parciales."""
    if not plan_rows:
        return Decimal('0.00')
    pendiente = Decimal('0.00')
    for row in plan_rows:
        pendiente += pendiente_cuota(row, abonado_por_cuota.get(row.numero_cuota, Decimal('0.00')))
    return round_money(pendiente)


def _partir_monto_cuota(aplicar: Decimal, cuota) -> tuple[Decimal, Decimal]:
    capital_prog = Decimal(cuota.capital_programado)
    interes_prog = Decimal(cuota.interes_programado)
    base = capital_prog + interes_prog
    if base <= 0:
        return round_money(aplicar), Decimal('0.00')
    capital = round_money(aplicar * capital_prog / base)
    interes = round_money(aplicar - capital)
    return capital, interes


def saldo_pendiente_tras_abono(
    plan_rows: list,
    abonado_previo: dict[int, Decimal],
    cuota_numero: int | None,
    capital: Decimal,
    interes: Decimal,
    mora: Decimal,
) -> Decimal:
    """Saldo pendiente (capital + interés) tras aplicar un abono a una cuota."""
    if not plan_rows or cuota_numero is None:
        return Decimal('0.00')
    abonado = dict(abonado_previo)
    abonado[cuota_numero] = abonado.get(cuota_numero, Decimal('0.00')) + capital + interes + mora
    return saldo_pendiente_con_abonos(plan_rows, abonado)


def distribuir_monto_en_cuotas(
    plan_rows: list,
    cuota_inicio: int,
    monto_distribuir: Decimal,
    mora_total: Decimal,
    abonado_previo: dict[int, Decimal],
) -> list[dict]:
    """
    Reparte ``monto_distribuir`` (capital+interés) desde ``cuota_inicio``.
    Devuelve líneas listas para crear registros ``Pago``.
    """
    if monto_distribuir <= 0 and mora_total <= 0:
        return []

    restante = round_money(monto_distribuir)
    mora_restante = round_money(mora_total)
    filas = sorted(
        (row for row in plan_rows if row.numero_cuota >= cuota_inicio),
        key=lambda row: row.numero_cuota,
    )
    lineas: list[dict] = []
    abonado_sim = dict(abonado_previo)

    for row in filas:
        if restante <= 0 and mora_restante <= 0:
            break
        pendiente = pendiente_cuota(row, abonado_sim.get(row.numero_cuota, Decimal('0.00')))
        if pendiente <= 0 and mora_restante <= 0:
            continue

        aplicar = min(restante, pendiente) if pendiente > 0 else Decimal('0.00')
        mora_linea = mora_restante if not lineas else Decimal('0.00')
        if aplicar <= 0 and mora_linea <= 0:
            continue

        capital, interes = _partir_monto_cuota(aplicar, row) if aplicar > 0 else (Decimal('0.00'), Decimal('0.00'))
        abonado_sim[row.numero_cuota] = abonado_sim.get(row.numero_cuota, Decimal('0.00')) + capital + interes + mora_linea
        lineas.append(
            {
                'numero_cuota': row.numero_cuota,
                'documento': f'Cuota {row.numero_cuota}',
                'capital': capital,
                'interes': interes,
                'mora': mora_linea,
                'saldo': saldo_pendiente_con_abonos(plan_rows, abonado_sim),
            }
        )
        restante = round_money(restante - aplicar)
        mora_restante = Decimal('0.00')

    return lineas
