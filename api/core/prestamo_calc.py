"""Cálculos de tasa y periodos para préstamos (interés simple por periodo)."""

from decimal import Decimal


def frecuencia_anual(forma_pago: str) -> int:
    """Número de periodos de cobro por año según forma de pago."""
    return {'mensual': 12, 'quincenal': 24, 'semanal': 52}[forma_pago]


def periodic_rate_from_nominal(tasa_nominal_pct: Decimal, forma_pago: str) -> Decimal:
    """Convierte tasa nominal mensual (%) a tasa por periodo."""
    if forma_pago == 'semanal':
        return tasa_nominal_pct / Decimal('4')
    if forma_pago == 'quincenal':
        return tasa_nominal_pct / Decimal('2')
    return tasa_nominal_pct


def periods_from_months(plazo_meses: int, forma_pago: str) -> int:
    """Convierte plazo en meses al número de cuotas/periodos."""
    if forma_pago == 'semanal':
        return plazo_meses * 4
    if forma_pago == 'quincenal':
        return plazo_meses * 2
    return plazo_meses


def annual_rate_from_nominal(tasa_nominal_pct: Decimal) -> Decimal:
    """Calcula la tasa anual efectiva desde una tasa nominal mensual."""
    tasa_nominal = tasa_nominal_pct / Decimal('100')
    tasa_anual = (Decimal('1') + tasa_nominal) ** 12 - Decimal('1')
    return tasa_anual * Decimal('100')


def plan_totales_desde_condiciones(
    monto: Decimal,
    plazo_meses: int,
    forma_pago: str,
    tasa_nominal_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """Calcula (total capital+interés del plan, monto de la primera cuota)."""
    from .money import round_money as _round

    periodos = periods_from_months(plazo_meses, forma_pago)
    tasa_periodica = periodic_rate_from_nominal(tasa_nominal_pct, forma_pago) / Decimal('100')
    capital_fijo = _round(monto / Decimal(periodos))
    interes_fijo = _round(monto * tasa_periodica)
    cuota_periodica = _round(capital_fijo + interes_fijo)

    saldo_capital = monto
    total = Decimal('0.00')
    primera_cuota = cuota_periodica

    for periodo in range(1, periodos + 1):
        capital = capital_fijo
        interes = interes_fijo
        if periodo == periodos:
            capital = saldo_capital
        total += _round(capital + interes)
        saldo_capital = _round(saldo_capital - capital)
        if saldo_capital < 0:
            saldo_capital = Decimal('0.00')

    return _round(total), primera_cuota
