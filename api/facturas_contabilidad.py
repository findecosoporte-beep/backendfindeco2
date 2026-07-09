"""Listado de facturas SAR emitidas para contabilidad."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from api.core.fechas_display import ahora_local_iso, cobrado_en_efectivo, formato_hora_hn
from api.core.money import round_money
from api.models import Cartera, Pago


def recolectar_facturas_contabilidad(
    inicio,
    fin,
    *,
    id_cartera: int | None = None,
    incluir_anuladas: bool = False,
) -> dict:
    qs = (
        Pago.objects.filter(
            fecha_pago__gte=inicio,
            fecha_pago__lte=fin,
        )
        .exclude(Q(numero_factura__isnull=True) | Q(numero_factura=''))
        .filter(id_pago_factura__isnull=True)
        .select_related(
            'id_prestamo',
            'id_prestamo__id_cliente',
            'id_prestamo__id_cartera',
        )
        .order_by('fecha_pago', 'numero_factura', 'id_pago')
    )
    if not incluir_anuladas:
        qs = qs.filter(anulado=False)

    cartera_etiqueta = 'Todas las carteras'
    if id_cartera is not None:
        qs = qs.filter(id_prestamo__id_cartera_id=id_cartera)
        cartera = Cartera.objects.filter(pk=id_cartera).only('nombre').first()
        if cartera:
            cartera_etiqueta = cartera.nombre

    filas = []
    tot_capital = Decimal('0.00')
    tot_interes = Decimal('0.00')
    tot_mora = Decimal('0.00')
    tot_cobrado = Decimal('0.00')

    for pg in qs:
        prestamo = pg.id_prestamo
        cliente = prestamo.id_cliente if prestamo else None
        cartera = prestamo.id_cartera if prestamo else None
        capital = Decimal(pg.capital)
        interes = Decimal(pg.interes)
        mora = Decimal(pg.mora)
        total = round_money(capital + interes + mora)
        if not pg.anulado:
            tot_capital += capital
            tot_interes += interes
            tot_mora += mora
            tot_cobrado += total
        filas.append(
            {
                'id_pago': pg.id_pago,
                'numero_factura': pg.numero_factura or '',
                'fecha_pago': pg.fecha_pago.isoformat(),
                'hora_pago': formato_hora_hn(cobrado_en_efectivo(pg)),
                'nombre_cliente': cliente.nombre if cliente else '',
                'dni_cliente': cliente.dni if cliente else '',
                'rtn_cliente': (cliente.rtn if cliente else '') or '',
                'numero_prestamo': prestamo.numero_prestamo if prestamo else '',
                'cartera_nombre': cartera.nombre if cartera else '',
                'capital': str(round_money(capital)),
                'interes': str(round_money(interes)),
                'mora': str(round_money(mora)),
                'total': str(total),
                'monto_recibido': str(
                    round_money(pg.monto_recibido_cliente)
                    if pg.monto_recibido_cliente is not None
                    else total
                ),
                'anulado': bool(pg.anulado),
                'estado': 'Anulada' if pg.anulado else 'Vigente',
            }
        )

    return {
        'fecha_inicio': inicio.isoformat(),
        'fecha_fin': fin.isoformat(),
        'generado_en': ahora_local_iso(),
        'cartera_etiqueta': cartera_etiqueta,
        'incluir_anuladas': incluir_anuladas,
        'filas': filas,
        'resumen': {
            'registros': len(filas),
            'total_capital': str(round_money(tot_capital)),
            'total_interes': str(round_money(tot_interes)),
            'total_mora': str(round_money(tot_mora)),
            'total_cobrado': str(round_money(tot_cobrado)),
        },
    }
