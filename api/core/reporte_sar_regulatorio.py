"""Reporte trimestral regulatorio SAR: cartera, desembolsos e ingresos por periodo."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from api.core.anulacion_pago import filtrar_pagos_vigentes
from api.core.distribucion_pago import (
    abonado_por_cuota_desde_pagos,
    cuotas_pagadas_completas,
)
from api.core.money import round_money
from api.core.reporte_saldos import saldos_reporte_integracion
from api.models import Pago, Prestamo, PrestamoCuota


ESTADOS_CARTERA_VIGENTE = ('activo', 'pendiente_aprobacion')
ESTADOS_CARTERA_VENCIDA = ('mora',)
ESTADOS_ABIERTOS_CARTERA = ESTADOS_CARTERA_VIGENTE + ESTADOS_CARTERA_VENCIDA


def rango_trimestre(anio: int, trimestre: int) -> tuple[date, date]:
    """Devuelve (inicio, fin) inclusive del trimestre 1-4."""
    if trimestre < 1 or trimestre > 4:
        raise ValueError('trimestre debe estar entre 1 y 4')
    mes_inicio = (trimestre - 1) * 3 + 1
    mes_fin = mes_inicio + 2
    inicio = date(anio, mes_inicio, 1)
    ultimo_dia = calendar.monthrange(anio, mes_fin)[1]
    fin = date(anio, mes_fin, ultimo_dia)
    return inicio, fin


def _auxiliar_saldos_prestamos(ids: list[int]) -> tuple[
    dict[int, list[PrestamoCuota]],
    dict[int, Decimal],
    dict[int, dict[int, Decimal]],
]:
    cuotas_por_prestamo: dict[int, list[PrestamoCuota]] = defaultdict(list)
    if ids:
        for c in PrestamoCuota.objects.filter(id_prestamo_id__in=ids).order_by(
            'id_prestamo_id', 'numero_cuota'
        ):
            cuotas_por_prestamo[c.id_prestamo_id].append(c)

    abonado_por_prestamo: dict[int, Decimal] = defaultdict(lambda: Decimal('0.00'))
    pagos_por_prestamo: dict[int, list[Pago]] = defaultdict(list)
    if ids:
        for pg in filtrar_pagos_vigentes(Pago.objects.filter(id_prestamo_id__in=ids)).only(
            'id_prestamo_id',
            'documento',
            'capital',
            'interes',
            'mora',
            'detalle_distribucion',
        ):
            pagos_por_prestamo[pg.id_prestamo_id].append(pg)
            abonado_por_prestamo[pg.id_prestamo_id] += (
                Decimal(pg.capital) + Decimal(pg.interes) + Decimal(pg.mora)
            )

    abonado_cuota_por_prestamo: dict[int, dict[int, Decimal]] = {}
    for pid in ids:
        abonado_cuota_por_prestamo[pid] = abonado_por_cuota_desde_pagos(
            pagos_por_prestamo.get(pid, [])
        )

    return cuotas_por_prestamo, abonado_por_prestamo, abonado_cuota_por_prestamo


def _saldo_pendiente_prestamo(
    prestamo: Prestamo,
    cuotas_por_prestamo: dict[int, list[PrestamoCuota]],
    abonado_por_prestamo: dict[int, Decimal],
    abonado_cuota_por_prestamo: dict[int, dict[int, Decimal]],
) -> Decimal:
    plan = cuotas_por_prestamo.get(prestamo.id_prestamo, [])
    abonado_total = abonado_por_prestamo.get(prestamo.id_prestamo, Decimal('0.00'))
    abonado_cuota = abonado_cuota_por_prestamo.get(prestamo.id_prestamo, {})
    paid_nums = cuotas_pagadas_completas(plan, abonado_cuota) if plan else set()
    _inicial, saldo_actual = saldos_reporte_integracion(
        prestamo,
        plan,
        abonado_cuota if plan else None,
        abonado_total,
        paid_nums=paid_nums,
    )
    return saldo_actual


def generar_reporte_sar_trimestral(anio: int, trimestre: int) -> dict:
    """Consolida métricas del trimestre para reporte regulatorio."""
    inicio, fin = rango_trimestre(anio, trimestre)

    otorgados_qs = Prestamo.objects.filter(fecha_entrega__gte=inicio, fecha_entrega__lte=fin)
    otorgados_agg = otorgados_qs.aggregate(
        total=Count('id_prestamo'),
        monto=Sum('monto'),
    )

    pagos_qs = filtrar_pagos_vigentes(
        Pago.objects.filter(fecha_pago__gte=inicio, fecha_pago__lte=fin)
    )
    pagos_agg = pagos_qs.aggregate(
        ingresos_intereses=Sum('interes'),
        pagos_capital=Sum('capital'),
        pagos_interes=Sum('interes'),
        pagos_mora=Sum('mora'),
    )
    ingresos_intereses = round_money(Decimal(pagos_agg['ingresos_intereses'] or 0))
    pagos_recibidos = round_money(
        Decimal(pagos_agg['pagos_capital'] or 0)
        + Decimal(pagos_agg['pagos_interes'] or 0)
        + Decimal(pagos_agg['pagos_mora'] or 0)
    )

    cartera_qs = Prestamo.objects.filter(
        estado__in=ESTADOS_ABIERTOS_CARTERA,
        fecha_entrega__lte=fin,
    )
    ids_cartera = list(cartera_qs.values_list('id_prestamo', flat=True))
    cuotas_map, abonado_map, abonado_cuota_map = _auxiliar_saldos_prestamos(ids_cartera)

    vigente_prestamos = 0
    vigente_saldo = Decimal('0.00')
    vencida_prestamos = 0
    vencida_saldo = Decimal('0.00')

    for prestamo in cartera_qs.iterator(chunk_size=200):
        saldo = _saldo_pendiente_prestamo(
            prestamo,
            cuotas_map,
            abonado_map,
            abonado_cuota_map,
        )
        if prestamo.estado in ESTADOS_CARTERA_VIGENTE:
            vigente_prestamos += 1
            vigente_saldo += saldo
        elif prestamo.estado in ESTADOS_CARTERA_VENCIDA:
            vencida_prestamos += 1
            vencida_saldo += saldo

    return {
        'trimestre': trimestre,
        'anio': anio,
        'fecha_inicio': inicio.isoformat(),
        'fecha_fin': fin.isoformat(),
        'total_prestamos_otorgados': int(otorgados_agg['total'] or 0),
        'monto_prestamos_otorgados': str(round_money(Decimal(otorgados_agg['monto'] or 0))),
        'cartera_vigente': {
            'prestamos': vigente_prestamos,
            'saldo': str(round_money(vigente_saldo)),
        },
        'cartera_vencida': {
            'prestamos': vencida_prestamos,
            'saldo': str(round_money(vencida_saldo)),
        },
        'ingresos_intereses': str(ingresos_intereses),
        'pagos_recibidos': str(pagos_recibidos),
    }
