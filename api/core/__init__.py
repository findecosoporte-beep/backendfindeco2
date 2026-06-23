"""Utilidades compartidas de dominio (dinero, cuotas, tasas, fechas)."""

from .cuotas import extract_cuota_numero_from_documento
from .fechas import (
    add_months,
    align_weekday_on_or_after,
    calculate_fecha_cuota,
    calculate_fecha_vencimiento,
    weekday_from_dia_cobro,
)
from .money import CENTS, round_money
from .prestamo_calc import (
    annual_rate_from_nominal,
    frecuencia_anual,
    periodic_rate_from_nominal,
    periods_from_months,
)

__all__ = [
    'CENTS',
    'add_months',
    'align_weekday_on_or_after',
    'annual_rate_from_nominal',
    'calculate_fecha_cuota',
    'calculate_fecha_vencimiento',
    'weekday_from_dia_cobro',
    'extract_cuota_numero_from_documento',
    'frecuencia_anual',
    'periodic_rate_from_nominal',
    'periods_from_months',
    'round_money',
]
