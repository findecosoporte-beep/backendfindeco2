"""Formato de fecha y hora para PDFs y reportes (zona America/Tegucigalpa)."""

from __future__ import annotations

from datetime import date, datetime, time

from django.utils import timezone

__all__ = [
    'ahora_local_iso',
    'cobrado_en_efectivo',
    'formato_fecha_hn',
    'formato_fecha_hora_hn',
    'formato_hora_hn',
]


def _asegurar_local(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def formato_fecha_hn(valor: date | datetime | None) -> str:
    if valor is None:
        return '—'
    if isinstance(valor, datetime):
        valor = _asegurar_local(valor).date()
    return valor.strftime('%d/%m/%Y')


def formato_hora_hn(valor: datetime | None) -> str:
    if valor is None:
        return '—'
    return _asegurar_local(valor).strftime('%I:%M %p')


def formato_fecha_hora_hn(valor: datetime | None) -> str:
    if valor is None:
        return '—'
    local = _asegurar_local(valor)
    return f'{local.strftime("%d/%m/%Y")} {local.strftime("%I:%M %p")}'


def ahora_local_iso() -> str:
    return timezone.localtime(timezone.now()).isoformat()


def cobrado_en_efectivo(pago) -> datetime:
    """Momento del cobro para factura/reportes; respaldo con mediodía si es histórico."""
    if getattr(pago, 'cobrado_en', None):
        return _asegurar_local(pago.cobrado_en)
    fecha = getattr(pago, 'fecha_pago', None)
    if fecha is None:
        return timezone.localtime(timezone.now())
    return _asegurar_local(
        timezone.make_aware(datetime.combine(fecha, time(12, 0)), timezone.get_current_timezone())
    )
