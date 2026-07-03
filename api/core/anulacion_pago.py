"""Anulación de cobros con reversión de saldos y auditoría."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import Pago, Prestamo, Usuario

__all__ = [
    'anular_grupo_cobro',
    'filtrar_pagos_vigentes',
    'grupo_cobro_desde_pago',
    'recalcular_estado_prestamo',
]


def filtrar_pagos_vigentes(qs: QuerySet) -> QuerySet:
    """Excluye pagos anulados de consultas operativas."""
    return qs.filter(anulado=False)


def grupo_cobro_desde_pago(pago: Pago) -> list[Pago]:
    """
    Devuelve todos los registros Pago del mismo cobro (maestro + líneas hijas).
    """
    maestro = pago
    if pago.monto_recibido_cliente is None and pago.id_pago_factura_id:
        maestro = (
            Pago.objects.filter(pk=pago.id_pago_factura_id).first() or pago
        )

    ids = {maestro.pk}
    for hijo in Pago.objects.filter(id_pago_factura_id=maestro.pk).only('id_pago'):
        ids.add(hijo.id_pago)

    return list(
        Pago.objects.filter(pk__in=ids).select_related('id_prestamo').order_by('id_pago')
    )


def _sync_prestamo_desde_ultimo_pago(prestamo: Prestamo, pago: Pago) -> None:
    """Actualiza estado y días de mora del préstamo según el último pago vigente."""
    saldo = Decimal(pago.saldo)
    mora = Decimal(pago.mora)
    dias_mora = 0
    if (
        pago.fecha_pago
        and prestamo.fecha_vencimiento
        and pago.fecha_pago > prestamo.fecha_vencimiento
    ):
        dias_mora = (pago.fecha_pago - prestamo.fecha_vencimiento).days

    if saldo <= 0:
        prestamo.estado = 'pagado'
        prestamo.dias_mora = 0
    elif mora > 0 or dias_mora > 0:
        prestamo.estado = 'mora'
        prestamo.dias_mora = max(dias_mora, prestamo.dias_mora)
    else:
        prestamo.estado = 'activo'
        prestamo.dias_mora = 0

    prestamo.save(update_fields=['estado', 'dias_mora'])


def _estado_prestamo_sin_pagos(prestamo: Prestamo) -> None:
    """Restablece estado cuando no quedan cobros vigentes."""
    hoy = date.today()
    if prestamo.fecha_vencimiento and hoy > prestamo.fecha_vencimiento:
        prestamo.estado = 'mora'
        prestamo.dias_mora = (hoy - prestamo.fecha_vencimiento).days
    else:
        prestamo.estado = 'activo'
        prestamo.dias_mora = 0
    prestamo.save(update_fields=['estado', 'dias_mora'])


def recalcular_estado_prestamo(prestamo: Prestamo) -> None:
    """Recalcula estado del préstamo a partir de pagos no anulados."""
    ultimo = (
        filtrar_pagos_vigentes(Pago.objects.filter(id_prestamo=prestamo))
        .order_by('-fecha_pago', '-id_pago')
        .first()
    )
    if ultimo is None:
        _estado_prestamo_sin_pagos(prestamo)
        return
    _sync_prestamo_desde_ultimo_pago(prestamo, ultimo)


@transaction.atomic
def anular_grupo_cobro(pago: Pago, actor: Usuario, motivo: str) -> list[Pago]:
    """
    Marca como anulado un cobro completo y recalcula el préstamo afectado.
    """
    motivo_limpio = (motivo or '').strip()
    if not motivo_limpio:
        raise ValidationError({'motivo': 'Indique el motivo de la anulación.'})

    grupo = grupo_cobro_desde_pago(pago)
    if any(pg.anulado for pg in grupo):
        raise ValidationError({'detail': 'Este cobro ya fue anulado.'})

    ahora = timezone.now()
    prestamo = grupo[0].id_prestamo
    Prestamo.objects.select_for_update().get(pk=prestamo.pk)

    for pg in grupo:
        pg.anulado = True
        pg.anulado_en = ahora
        pg.anulado_por = actor
        pg.motivo_anulacion = motivo_limpio
        pg.save(update_fields=['anulado', 'anulado_en', 'anulado_por', 'motivo_anulacion'])

    recalcular_estado_prestamo(prestamo)
    return grupo
