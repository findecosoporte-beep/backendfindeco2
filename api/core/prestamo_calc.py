"""Cálculos de tasa y periodos para préstamos (interés simple por periodo)."""

from decimal import Decimal


def frecuencia_anual(forma_pago: str) -> int:
    """Número de periodos de cobro por año según forma de pago."""
    return {'mensual': 12, 'quincenal': 24, 'semanal': 52}[forma_pago]


def periodic_rate_from_nominal(tasa_nominal_pct: Decimal, forma_pago: str) -> Decimal:
    """Convierte tasa nominal mensual (%) a tasa por periodo (mensual/quincenal)."""
    if forma_pago == 'quincenal':
        return tasa_nominal_pct / Decimal('2')
    return tasa_nominal_pct


def tasa_semanal_negocio(semanas: int) -> Decimal:
    """Tasa de interés simple por semana según reglas FINDECO.

    - 6 semanas: 2.5% semanal (15% total).
    - 8 semanas: 2.5% semanal (20% total).
    - 10 semanas: 2.5% semanal (25% total).
    - 12 semanas: 2.5% semanal (30% total).
    - 16 semanas: 2.5% semanal (40% total).
    - Resto: 10% semanal.
    """
    if semanas in (6, 8, 10, 12, 16):
        return Decimal('2.5')
    return Decimal('10')


def interes_total_pct_semanal(semanas: int) -> Decimal:
    """Interés total del crédito (%) para préstamos semanales."""
    return tasa_semanal_negocio(semanas) * Decimal(semanas)


def tasa_periodica_para_calculo(
    tasa_nominal_pct: Decimal,
    forma_pago: str,
    plazo: int,
) -> Decimal:
    """Porcentaje por cuota usado en interés simple."""
    if forma_pago == 'semanal':
        return tasa_semanal_negocio(plazo)
    return periodic_rate_from_nominal(tasa_nominal_pct, forma_pago)


def periodos_desde_plazo(plazo: int, forma_pago: str) -> int:
    """Número de cuotas. En semanal ``plazo`` son semanas; en mensual/quincenal, meses."""
    if forma_pago == 'semanal':
        return plazo
    if forma_pago == 'quincenal':
        return plazo * 2
    return plazo


def periods_from_months(plazo_meses: int, forma_pago: str) -> int:
    """Alias histórico; ver ``periodos_desde_plazo``."""
    return periodos_desde_plazo(plazo_meses, forma_pago)


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

    periodos = periodos_desde_plazo(plazo_meses, forma_pago)
    tasa_periodica = tasa_periodica_para_calculo(tasa_nominal_pct, forma_pago, plazo_meses) / Decimal('100')
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
