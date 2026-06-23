"""Saldos del reporte de cobros: capital + intereses comprometidos y pendientes."""

from decimal import Decimal

from .money import round_money
from .prestamo_calc import plan_totales_desde_condiciones


def monto_cuota_programada(cuota) -> Decimal:
    """Total de una cuota del plan (cuota + servicios + otros)."""
    return round_money(
        Decimal(cuota.total_programado)
        + Decimal(cuota.servicios_programado or 0)
        + Decimal(cuota.otros_programado or 0)
    )


def total_compromiso_desde_plan(plan_rows: list) -> Decimal:
    """Suma capital + intereses de todas las cuotas programadas."""
    if not plan_rows:
        return Decimal('0.00')
    return round_money(sum(monto_cuota_programada(row) for row in plan_rows))


def saldo_pendiente_desde_plan(
    plan_rows: list,
    abonado_por_cuota: dict[int, Decimal] | None = None,
    paid_nums: set[int] | None = None,
) -> Decimal:
    """Suma pendiente por cuota; admite abonos parciales o conjunto de cuotas pagadas."""
    if not plan_rows:
        return Decimal('0.00')
    if abonado_por_cuota is not None:
        from .distribucion_pago import saldo_pendiente_con_abonos

        return saldo_pendiente_con_abonos(plan_rows, abonado_por_cuota)
    if paid_nums is None:
        paid_nums = set()
    return round_money(
        sum(
            monto_cuota_programada(row)
            for row in plan_rows
            if row.numero_cuota not in paid_nums
        )
    )


def total_compromiso_desde_prestamo(prestamo) -> Decimal:
    """Estima capital + intereses cuando el préstamo no tiene plan persistido."""
    total, _ = plan_totales_desde_condiciones(
        Decimal(prestamo.monto),
        int(prestamo.plazo),
        prestamo.forma_pago,
        Decimal(prestamo.tasa_interes),
    )
    return total


def saldos_reporte_integracion(
    prestamo,
    plan_rows: list,
    abonado_por_cuota: dict[int, Decimal] | None,
    abonado_total: Decimal,
    paid_nums: set[int] | None = None,
) -> tuple[Decimal, Decimal]:
    """
    Retorna (saldo_inicial, saldo_actual) para la hoja de cobros.

    - saldo_inicial: monto desembolsado + intereses totales del plan.
    - saldo_actual: lo que aún falta por pagar (incluye descuento por abonos parciales).
    """
    if plan_rows:
        saldo_inicial = total_compromiso_desde_plan(plan_rows)
        if abonado_por_cuota is not None:
            saldo_actual = saldo_pendiente_desde_plan(plan_rows, abonado_por_cuota=abonado_por_cuota)
        else:
            saldo_actual = saldo_pendiente_desde_plan(plan_rows, paid_nums=paid_nums or set())
        return saldo_inicial, saldo_actual

    saldo_inicial = total_compromiso_desde_prestamo(prestamo)
    saldo_actual = round_money(max(Decimal('0.00'), saldo_inicial - abonado_total))
    return saldo_inicial, saldo_actual
