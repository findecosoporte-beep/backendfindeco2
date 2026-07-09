"""Distribución de cobros: abonos parciales quedan en la misma cuota sin interés adicional."""

from collections import defaultdict
from decimal import Decimal

from .cuotas import extract_cuota_numero_from_documento
from .money import round_money
from .movimientos_pago import abonado_por_cuota_desde_pagos as _abonado_por_cuota_desde_pagos
from .reporte_saldos import monto_cuota_programada

CUOTA_PAGADA_TOLERANCIA = Decimal('0.01')

__all__ = [
    'CUOTA_PAGADA_TOLERANCIA',
    'abonado_por_cuota_desde_pagos',
    'cuota_esta_pagada',
    'cuotas_cubiertas_por_pago_acumulado',
    'cuotas_pagadas_completas',
    'distribuir_cobro_con_excedente_a_capital',
    'distribuir_monto_en_cuotas',
    'pendiente_cuota',
    'saldo_pendiente_con_abonos',
    'saldo_pendiente_tras_abono',
    'total_abonado_prestamo',
]


def total_abonado_prestamo(pagos) -> Decimal:
    """Suma capital+interés+mora de TODOS los pagos del préstamo (incluye abono a capital)."""
    return round_money(
        sum((Decimal(pg.capital) + Decimal(pg.interes) + Decimal(pg.mora) for pg in pagos), Decimal('0.00'))
    )


def abonado_por_cuota_desde_pagos(pagos) -> dict[int, Decimal]:
    """Suma capital+interés+mora abonado por número de cuota (incluye detalle_distribucion)."""
    return _abonado_por_cuota_desde_pagos(pagos)


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


def cuotas_cubiertas_por_pago_acumulado(plan_rows: list, abonado_total: Decimal) -> set[int]:
    """
    Cuotas cubiertas al consumir, en orden, TODO lo pagado en el préstamo (incluye
    abonos a capital, sin importar con qué documento se registró cada pago).

    Sirve para saber qué cuotas ya no se pueden volver a cobrar cuando el cliente
    adelantó varias cuotas de una sola vez (el excedente entra como abono a capital,
    pero de todas formas cubre esas cuotas futuras en orden).
    """
    if not plan_rows:
        return set()
    acumulado_objetivo = Decimal('0.00')
    cubiertas: set[int] = set()
    for row in sorted(plan_rows, key=lambda r: r.numero_cuota):
        acumulado_objetivo += monto_cuota_programada(row)
        if abonado_total >= acumulado_objetivo - CUOTA_PAGADA_TOLERANCIA:
            cubiertas.add(row.numero_cuota)
        else:
            break
    return cubiertas


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


def _compromiso_total_plan(plan_rows: list) -> Decimal:
    return round_money(sum(monto_cuota_programada(row) for row in plan_rows))


def _saldo_tras_monto_pagado(plan_rows: list, pagado_previo: Decimal, pagado_en_cobro: Decimal) -> Decimal:
    compromiso = _compromiso_total_plan(plan_rows)
    return round_money(max(Decimal('0.00'), compromiso - pagado_previo - pagado_en_cobro))


def distribuir_cobro_con_excedente_a_capital(
    plan_rows: list,
    cuota_inicio: int,
    monto_distribuir: Decimal,
    mora_total: Decimal,
    abonado_previo: dict[int, Decimal],
) -> list[dict]:
    """
    Aplica el cobro a la cuota en curso; lo que excede el pendiente de esa cuota
    se registra como abono a capital (no avanza a la siguiente cuota).
    """
    if monto_distribuir <= 0 and mora_total <= 0:
        return []

    fila_inicio = next((row for row in plan_rows if row.numero_cuota == cuota_inicio), None)
    if fila_inicio is None:
        return []

    pendiente = pendiente_cuota(fila_inicio, abonado_previo.get(cuota_inicio, Decimal('0.00')))
    restante = round_money(monto_distribuir)
    mora_restante = round_money(mora_total)
    pagado_previo = round_money(sum(abonado_previo.values(), Decimal('0.00')))
    pagado_en_cobro = Decimal('0.00')
    lineas: list[dict] = []

    aplicar_cuota = min(restante, pendiente) if pendiente > 0 else Decimal('0.00')
    if aplicar_cuota > 0 or mora_restante > 0:
        capital, interes = (
            _partir_monto_cuota(aplicar_cuota, fila_inicio)
            if aplicar_cuota > 0
            else (Decimal('0.00'), Decimal('0.00'))
        )
        monto_linea = round_money(capital + interes + mora_restante)
        pagado_en_cobro += monto_linea
        es_parcial = (
            pendiente > 0
            and aplicar_cuota < pendiente - CUOTA_PAGADA_TOLERANCIA
        )
        lineas.append(
            {
                'numero_cuota': cuota_inicio,
                'documento': f'Cuota {cuota_inicio}',
                'capital': capital,
                'interes': interes,
                'mora': mora_restante,
                'saldo': _saldo_tras_monto_pagado(plan_rows, pagado_previo, pagado_en_cobro),
                'parcial': es_parcial,
            }
        )
        restante = round_money(restante - aplicar_cuota)
        mora_restante = Decimal('0.00')

    excedente = restante
    if excedente > 0:
        pagado_en_cobro += excedente
        saldo_tras_abono = _saldo_tras_monto_pagado(plan_rows, pagado_previo, pagado_en_cobro)
        lineas.append(
            {
                'numero_cuota': None,
                'abono_capital': True,
                'documento': 'Abono a capital',
                'capital': excedente,
                'interes': Decimal('0.00'),
                'mora': Decimal('0.00'),
                'saldo': saldo_tras_abono,
                # El abono cubrió todo lo comprometido del plan: el préstamo queda liquidado.
                'liquida_prestamo': saldo_tras_abono <= Decimal('0.00'),
            }
        )

    return lineas


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
        es_parcial = (
            pendiente > 0
            and aplicar < pendiente - CUOTA_PAGADA_TOLERANCIA
        )
        lineas.append(
            {
                'numero_cuota': row.numero_cuota,
                'documento': f'Cuota {row.numero_cuota}',
                'capital': capital,
                'interes': interes,
                'mora': mora_linea,
                'saldo': saldo_pendiente_con_abonos(plan_rows, abonado_sim),
                'parcial': es_parcial,
            }
        )
        restante = round_money(restante - aplicar)
        mora_restante = Decimal('0.00')

    if restante > 0:
        pagado_previo = round_money(sum(abonado_previo.values(), Decimal('0.00')))
        pagado_en_cobro = round_money(monto_distribuir - restante)
        saldo_tras_abono = _saldo_tras_monto_pagado(plan_rows, pagado_previo, pagado_en_cobro + restante)
        lineas.append(
            {
                'numero_cuota': None,
                'abono_capital': True,
                'documento': 'Abono a capital',
                'capital': restante,
                'interes': Decimal('0.00'),
                'mora': Decimal('0.00'),
                'saldo': saldo_tras_abono,
                'liquida_prestamo': saldo_tras_abono <= Decimal('0.00'),
            }
        )
    elif lineas and lineas[-1]['saldo'] <= Decimal('0.00'):
        lineas[-1]['liquida_prestamo'] = True

    return lineas
