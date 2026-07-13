"""Exportación PDF del estado de cuenta por préstamo."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .core.cuotas import extract_cuota_numero_from_documento
from .core.distribucion_pago import cuotas_cubiertas_por_pago_acumulado, pendiente_cuota, total_abonado_prestamo
from .core.movimientos_pago import (
    abonado_por_cuota_desde_movimientos,
    cuota_pago_desde_movimientos,
)
from .core.fechas_display import ahora_local_iso, cobrado_en_efectivo, formato_fecha_hn, formato_fecha_hora_hn, formato_hora_hn
from .core.findeco_brand import platypus_logo_findeco
from .core.money import round_money
from .core.prestamo_calc import plan_totales_desde_condiciones
from .core.reporte_saldos import monto_cuota_programada
from .models import Pago, Prestamo, PrestamoCuota

ETIQUETAS_ESTADO_PRESTAMO = {
    'pendiente_aprobacion': 'Pendiente aprobación',
    'activo': 'Activo',
    'pagado': 'Pagado',
    'mora': 'Mora',
    'cancelado': 'Cancelado',
}

ETIQUETAS_FORMA_PAGO = {
    'semanal': 'SEMANAL',
    'quincenal': 'QUINCENAL',
    'mensual': 'MENSUAL',
}

ETIQUETAS_FORMA_DESEMBOLSO = {
    'efectivo': 'Efectivo (E)',
    'transferencia': 'Transferencia (T)',
    'cheque': 'Cheque (C)',
}

_DESGLOSE_KEYS = ('capital', 'intereses', 'servicios', 'moratorios')

MARGIN_H_MM = 14
# Ancho útil carta (letter) menos márgenes laterales del documento.
TABLE_WIDTH_MM = (letter[0] / mm) - (2 * MARGIN_H_MM)
_COL_RATIO_PLAN_CUOTAS = (10, 22, 24, 24, 20, 22, 18)


def _anchos_tabla_plan_cuotas() -> list[float]:
    total_ratio = sum(_COL_RATIO_PLAN_CUOTAS)
    return [TABLE_WIDTH_MM * ratio / total_ratio * mm for ratio in _COL_RATIO_PLAN_CUOTAS]


def _format_fecha(iso: str | None) -> str:
    if not iso:
        return '—'
    try:
        y, m, d = iso.split('-')
        return f'{d}/{m}/{y}'
    except ValueError:
        return iso


def _money_pdf(value: str | Decimal | float | int) -> str:
    try:
        n = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return str(value)
    return f'L {n:,.2f}'


def _money_plain(value: str | Decimal | float | int) -> str:
    try:
        n = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return str(value)
    return f'{n:,.2f}'


def _etiqueta_forma_pago(forma: str | None) -> str:
    if not forma:
        return '—'
    return ETIQUETAS_FORMA_PAGO.get(forma, forma.upper())


def _etiqueta_forma_desembolso(forma: str | None) -> str:
    if not forma:
        return '—'
    return ETIQUETAS_FORMA_DESEMBOLSO.get(forma, forma)


def _desglose_cuota_plan(cuota: PrestamoCuota) -> dict[str, Decimal]:
    return {
        'capital': Decimal(cuota.capital_programado),
        'intereses': Decimal(cuota.interes_programado),
        'servicios': Decimal(cuota.servicios_programado or 0) + Decimal(cuota.otros_programado or 0),
        'moratorios': Decimal('0.00'),
    }


def _sumar_desglose(
    a: dict[str, Decimal],
    b: dict[str, Decimal],
) -> dict[str, Decimal]:
    return {k: round_money(a[k] + b[k]) for k in _DESGLOSE_KEYS}


def _restar_desglose(
    inicial: dict[str, Decimal],
    abonos: dict[str, Decimal],
) -> dict[str, Decimal]:
    return {k: round_money(max(Decimal('0.00'), inicial[k] - abonos[k])) for k in _DESGLOSE_KEYS}


def _total_desglose(d: dict[str, Decimal]) -> Decimal:
    return round_money(sum(d[k] for k in _DESGLOSE_KEYS))


def _desglose_pendiente_cuota(cuota: PrestamoCuota, abonado: Decimal) -> dict[str, Decimal]:
    base = _desglose_cuota_plan(cuota)
    total_prog = monto_cuota_programada(cuota)
    pendiente = pendiente_cuota(cuota, abonado)
    if pendiente <= 0 or total_prog <= 0:
        return {k: Decimal('0.00') for k in _DESGLOSE_KEYS}
    ratio = pendiente / total_prog
    return {
        'capital': round_money(base['capital'] * ratio),
        'intereses': round_money(base['intereses'] * ratio),
        'servicios': round_money(base['servicios'] * ratio),
        'moratorios': Decimal('0.00'),
    }


def _calcular_resumen_saldos(
    cuotas: list[PrestamoCuota],
    pagos: list[Pago],
    filas_cuotas: list[dict],
    abonado_por_cuota: dict[int, Decimal],
) -> dict:
    hoy = timezone.localdate()
    inicial = {k: Decimal('0.00') for k in _DESGLOSE_KEYS}
    for cuota in cuotas:
        inicial = _sumar_desglose(inicial, _desglose_cuota_plan(cuota))

    abonos = {k: Decimal('0.00') for k in _DESGLOSE_KEYS}
    for pago in pagos:
        abonos['capital'] += Decimal(pago.capital)
        abonos['intereses'] += Decimal(pago.interes)
        abonos['moratorios'] += Decimal(pago.mora)
    for k in abonos:
        abonos[k] = round_money(abonos[k])

    cuotas_por_num = {c.numero_cuota: c for c in cuotas}
    for fila in filas_cuotas:
        if fila.get('estado') != 'Pagada':
            continue
        cuota = cuotas_por_num.get(fila.get('numero_cuota'))
        if cuota is None:
            continue
        serv = Decimal(cuota.servicios_programado or 0) + Decimal(cuota.otros_programado or 0)
        abonos['servicios'] = round_money(abonos['servicios'] + serv)

    actual = _restar_desglose(inicial, abonos)

    vencido = {k: Decimal('0.00') for k in _DESGLOSE_KEYS}
    fecha_pago_vencido: date | None = None
    for fila in filas_cuotas:
        if fila.get('estado') != 'Pendiente':
            continue
        fecha_iso = (fila.get('fecha_programada') or '')[:10]
        if not fecha_iso:
            continue
        try:
            fecha_d = date.fromisoformat(fecha_iso)
        except ValueError:
            continue
        if fecha_d > hoy:
            continue
        cuota = cuotas_por_num.get(fila.get('numero_cuota'))
        if cuota is None:
            continue
        abonado = abonado_por_cuota.get(fila.get('numero_cuota'), Decimal('0.00'))
        vencido = _sumar_desglose(vencido, _desglose_pendiente_cuota(cuota, abonado))
        if fecha_pago_vencido is None or fecha_d < fecha_pago_vencido:
            fecha_pago_vencido = fecha_d

    if fecha_pago_vencido is None:
        pendientes = [f for f in filas_cuotas if f.get('estado') == 'Pendiente']
        if pendientes:
            prox = min(pendientes, key=lambda f: f.get('fecha_programada', ''))
            prox_iso = (prox.get('fecha_programada') or '')[:10]
            if prox_iso:
                try:
                    fecha_pago_vencido = date.fromisoformat(prox_iso)
                except ValueError:
                    fecha_pago_vencido = None

    filas_resumen = []
    for etiqueta, key in (
        ('Capital', 'capital'),
        ('Intereses', 'intereses'),
        ('Servicios', 'servicios'),
        ('Intereses Moratorios', 'moratorios'),
    ):
        filas_resumen.append(
            {
                'etiqueta': etiqueta,
                'inicial': str(round_money(inicial[key])),
                'abonos': str(round_money(abonos[key])),
                'actual': str(round_money(actual[key])),
                'vencido': str(round_money(vencido[key])),
                'es_total': False,
            }
        )
    filas_resumen.append(
        {
            'etiqueta': 'Total',
            'inicial': str(_total_desglose(inicial)),
            'abonos': str(_total_desglose(abonos)),
            'actual': str(_total_desglose(actual)),
            'vencido': str(_total_desglose(vencido)),
            'es_total': True,
        }
    )

    return {
        'filas': filas_resumen,
        'fecha_pago_vencido': fecha_pago_vencido.isoformat() if fecha_pago_vencido else None,
    }


def _estilo_tabla_datos() -> TableStyle:
    return TableStyle(
        [
            ('BACKGROUND', (0, 0), (-1, 0), colors.black),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
    )


def _etiqueta_documento_abono(pago: Pago) -> str:
    detalle = pago.detalle_distribucion or []
    if isinstance(detalle, list) and detalle:
        partes: list[str] = []
        for linea in detalle:
            if not isinstance(linea, dict):
                continue
            if linea.get('abono_capital'):
                partes.append(
                    'Abono a capital (liquida)'
                    if linea.get('liquida_prestamo')
                    else 'Abono a capital'
                )
                continue
            cuota = linea.get('cuota')
            if cuota is None:
                continue
            base = f'Cuota {cuota}'
            partes.append(f'{base} (parcial)' if linea.get('parcial') else base)
        unicas: list[str] = []
        vistos: set[str] = set()
        for p in partes:
            if p not in vistos:
                vistos.add(p)
                unicas.append(p)
        if unicas:
            return ', '.join(unicas)
    doc = (pago.documento or '').strip()
    return doc or f'Pago {pago.id_pago}'


def pago_por_cuota_con_fallback(cuotas: list[PrestamoCuota], pagos_ordenados: list[Pago]) -> dict[int, Pago]:
    """Asigna pagos a cuotas usando movimientos tipo cuota."""
    mapa_refs = cuota_pago_desde_movimientos(pagos_ordenados)
    pago_por_id = {p.id_pago: p for p in pagos_ordenados}
    resultado: dict[int, Pago] = {}
    for numero, ref in mapa_refs.items():
        pago = pago_por_id.get(ref['id_pago'])
        if pago is not None:
            resultado[numero] = pago
    if resultado:
        return resultado
    # Compatibilidad con pagos antiguos sin detalle_distribucion.
    mapa: dict[int, Pago] = {}
    usados: set[int] = set()
    for pago in pagos_ordenados:
        numero = extract_cuota_numero_from_documento(pago.documento)
        if numero is not None and numero not in mapa:
            mapa[numero] = pago
            usados.add(pago.id_pago)
    sin_asignar = [p for p in pagos_ordenados if p.id_pago not in usados]
    libres = sorted(c.numero_cuota for c in cuotas if c.numero_cuota not in mapa)
    for idx, cuota_num in enumerate(libres):
        if idx >= len(sin_asignar):
            break
        mapa[cuota_num] = sin_asignar[idx]
    return mapa


def recolectar_datos_estado_cuenta(prestamo: Prestamo) -> dict:
    cliente = prestamo.id_cliente
    cartera = prestamo.id_cartera
    cuotas = list(
        PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota'),
    )
    pagos = list(
        Pago.objects.filter(id_prestamo=prestamo, anulado=False).order_by('fecha_pago', 'id_pago'),
    )
    pago_map = pago_por_cuota_con_fallback(cuotas, pagos)
    abonado_por_cuota = abonado_por_cuota_desde_movimientos(pagos)

    # Cuotas cubiertas por el acumulado total pagado (aunque el excedente haya
    # quedado como abono a capital y no como "Cuota N" de cada una): el cliente
    # pudo adelantar varias cuotas de una sola vez, con o sin liquidar todo el plan.
    abonado_total = total_abonado_prestamo(pagos)
    cubiertas_por_acumulado = cuotas_cubiertas_por_pago_acumulado(cuotas, abonado_total)
    ultimo_pago = pagos[-1] if pagos else None

    filas_cuotas = []
    tot_plan_capital = Decimal('0.00')
    tot_plan_interes = Decimal('0.00')
    tot_plan_total = Decimal('0.00')
    for cuota in cuotas:
        pago = pago_map.get(cuota.numero_cuota)
        abonado_cuota = abonado_por_cuota.get(cuota.numero_cuota, Decimal('0.00'))
        total_cuota = monto_cuota_programada(cuota)
        capital = round_money(Decimal(cuota.capital_programado))
        interes = round_money(Decimal(cuota.interes_programado))
        saldo_cap = round_money(Decimal(cuota.saldo_capital_programado))
        tot_plan_capital += capital
        tot_plan_interes += interes
        tot_plan_total += total_cuota
        if pago is not None or abonado_cuota >= total_cuota - Decimal('0.01'):
            estado = 'Pagada'
            ref_pago = pago or ultimo_pago
            fecha_pago_val = ref_pago.fecha_pago.isoformat() if ref_pago else ''
            hora_val = formato_hora_hn(cobrado_en_efectivo(ref_pago)) if ref_pago else ''
            documento_val = f'Cuota {cuota.numero_cuota}'
        elif cuota.numero_cuota in cubiertas_por_acumulado and ultimo_pago is not None:
            estado = 'Pagada'
            fecha_pago_val = ultimo_pago.fecha_pago.isoformat()
            hora_val = formato_hora_hn(cobrado_en_efectivo(ultimo_pago))
            documento_val = f'Cuota {cuota.numero_cuota}'
        else:
            estado = 'Pendiente'
            fecha_pago_val = ''
            hora_val = ''
            documento_val = ''
        filas_cuotas.append(
            {
                'numero_cuota': cuota.numero_cuota,
                'fecha_programada': cuota.fecha_programada.isoformat(),
                'capital_programado': str(capital),
                'interes_programado': str(interes),
                'total_programado': str(round_money(total_cuota)),
                'saldo_capital': str(saldo_cap),
                'estado': estado,
                'fecha_pago': fecha_pago_val,
                'fecha_cancelo': fecha_pago_val,
                'hora_pago': hora_val,
                'documento': documento_val,
            }
        )

    tot_capital = Decimal('0.00')
    tot_interes = Decimal('0.00')
    for pago in pagos:
        tot_capital += Decimal(pago.capital)
        tot_interes += Decimal(pago.interes)
    total_abonado = round_money(tot_capital + tot_interes)

    filas_abonos = []
    saldo_cap_corrido = round_money(Decimal(prestamo.monto))
    conteo_documento: dict[str, int] = {}
    for idx, pago in enumerate(pagos, start=1):
        capital = round_money(Decimal(pago.capital))
        interes = round_money(Decimal(pago.interes))
        mora = round_money(Decimal(pago.mora or 0))
        saldo_cap_corrido = round_money(max(Decimal('0.00'), saldo_cap_corrido - capital))
        documento = _etiqueta_documento_abono(pago)
        clave = documento.lower()
        visto = conteo_documento.get(clave, 0) + 1
        conteo_documento[clave] = visto
        detalle = pago.detalle_distribucion or []
        if visto > 1 and not (isinstance(detalle, list) and len(detalle) > 0):
            documento = f'{documento} ({visto})'
        filas_abonos.append(
            {
                'n': idx,
                'fecha_pago': pago.fecha_pago.isoformat(),
                'documento': documento,
                'capital': str(capital),
                'interes': str(interes),
                'total': str(round_money(capital + interes + mora)),
                'saldo_capital': str(saldo_cap_corrido),
                'id_pago': pago.id_pago,
            }
        )

    tot_abonos_capital = round_money(sum((Decimal(f['capital']) for f in filas_abonos), Decimal('0.00')))
    tot_abonos_interes = round_money(sum((Decimal(f['interes']) for f in filas_abonos), Decimal('0.00')))
    tot_abonos_total = round_money(sum((Decimal(f['total']) for f in filas_abonos), Decimal('0.00')))
    tot_abonos_saldo = (
        round_money(Decimal(filas_abonos[-1]['saldo_capital'])) if filas_abonos else round_money(Decimal(prestamo.monto))
    )

    cuotas_pendientes = [f for f in filas_cuotas if f['estado'] == 'Pendiente']
    cuotas_pagadas = [f for f in filas_cuotas if f['estado'] == 'Pagada']

    interes_planificado = round_money(sum(Decimal(c.interes_programado) for c in cuotas))
    usuario = prestamo.id_usuario
    asesor_txt = (prestamo.asesor or '').strip() or (getattr(usuario, 'nombre', None) or '').strip()
    telefono = ((cliente.telefono if cliente else '') or '').strip()
    resumen_saldos = _calcular_resumen_saldos(cuotas, pagos, filas_cuotas, abonado_por_cuota)

    historial_filas = []
    if cliente is not None:
        prestamos_cliente = list(
            Prestamo.objects.filter(id_cliente=cliente).order_by('-fecha_entrega', '-id_prestamo'),
        )
        saldos_por_id: dict[int, Decimal] = {}
        for p in prestamos_cliente:
            ult = (
                Pago.objects.filter(id_prestamo=p, anulado=False)
                .order_by('-fecha_pago', '-id_pago')
                .only('saldo')
                .first()
            )
            if p.estado in ('pagado', 'cancelado'):
                saldos_por_id[p.id_prestamo] = Decimal('0.00')
            elif ult is not None:
                saldos_por_id[p.id_prestamo] = round_money(Decimal(ult.saldo))
            else:
                saldos_por_id[p.id_prestamo] = round_money(Decimal(p.monto))

        for p in prestamos_cliente:
            monto = round_money(Decimal(p.monto))
            tasa = Decimal(p.tasa_interes)
            plazo = int(p.plazo or 0)
            forma = p.forma_pago or 'mensual'
            if plazo > 0 and monto > 0:
                total_plan, _ = plan_totales_desde_condiciones(monto, plazo, forma, tasa)
                interes_hist = round_money(total_plan - monto)
            else:
                interes_hist = Decimal('0.00')
            historial_filas.append(
                {
                    'id_prestamo': p.id_prestamo,
                    'prestamo': (p.numero_prestamo or '').strip() or str(p.id_prestamo),
                    'monto': str(monto),
                    'interes': str(interes_hist),
                    'plazo': plazo,
                    'tasa': str(round_money(tasa)),
                    'producto': (p.producto or '').strip() or '—',
                    'saldo': str(saldos_por_id.get(p.id_prestamo, monto)),
                    'estado': p.estado,
                }
            )

    ficha = {
        'cliente': f'{cliente.id_cliente} — {cliente.nombre}' if cliente else '',
        'identidad': (cliente.dni if cliente else '') or '—',
        'supervisor': (prestamo.supervisor or '').strip() or '—',
        'asesor': asesor_txt or '—',
        'garantia': (prestamo.tipo_garantia or '').strip() or '—',
        'ciclos': str(prestamo.ciclos if prestamo.ciclos is not None else '—'),
        'telefono_celular': telefono or '—',
        'direccion': (cliente.direccion_residencia if cliente else '') or '',
        'monto_desembolsado': str(round_money(prestamo.monto)),
        'forma_desembolso': _etiqueta_forma_desembolso(prestamo.forma_desembolso),
        'forma_pago': _etiqueta_forma_pago(prestamo.forma_pago),
        'fecha_entrega': prestamo.fecha_entrega.isoformat(),
        'fecha_vencimiento': prestamo.fecha_vencimiento.isoformat(),
        'producto': (prestamo.producto or '').strip() or '—',
        'interes_planificado': str(interes_planificado),
        'tasa_interes': str(prestamo.tasa_interes),
        'dias_mora': str(prestamo.dias_mora if prestamo.dias_mora is not None else 0),
        'categoria': (prestamo.categoria or '').strip() or '—',
    }

    return {
        'numero_prestamo': prestamo.numero_prestamo,
        'nombre_cliente': cliente.nombre if cliente else '',
        'dni_cliente': (cliente.dni if cliente else '') or '',
        'telefono_cliente': telefono,
        'cartera_nombre': (cartera.nombre if cartera else '') or '',
        'estado_prestamo': ETIQUETAS_ESTADO_PRESTAMO.get(prestamo.estado, prestamo.estado),
        'fecha_emision': ahora_local_iso(),
        'ficha': ficha,
        'resumen_saldos': resumen_saldos,
        'cuotas': filas_cuotas,
        'plan_pagos': filas_cuotas,
        'plan_pagos_totales': {
            'capital': str(round_money(tot_plan_capital)),
            'interes': str(round_money(tot_plan_interes)),
            'total': str(round_money(tot_plan_total)),
            # Último saldo capital programado (no suma de saldos intermedios).
            'saldo_capital': str(
                round_money(Decimal(filas_cuotas[-1]['saldo_capital'])) if filas_cuotas else Decimal('0.00')
            ),
        },
        'cuotas_pendientes': cuotas_pendientes,
        'cuotas_pagadas': cuotas_pagadas,
        'abonos': filas_abonos,
        'abonos_totales': {
            'capital': str(tot_abonos_capital),
            'interes': str(tot_abonos_interes),
            'total': str(tot_abonos_total),
            'saldo_capital': str(tot_abonos_saldo),
        },
        'abonos_capital': [],
        'historial_prestamos': historial_filas,
        'resumen': {
            'cuotas_pagadas': len(cuotas_pagadas),
            'cuotas_pendientes': len(cuotas_pendientes),
            'total_abonado': str(total_abonado),
            'total_capital': str(round_money(tot_capital)),
            'total_interes': str(round_money(tot_interes)),
            'total_pagos': len(pagos),
        },
    }


def exportar_estado_cuenta_pdf(datos: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'EcTitle',
        parent=styles['Heading1'],
        fontSize=13,
        alignment=1,
        spaceAfter=4,
        textColor=colors.black,
    )
    meta_style = ParagraphStyle(
        'EcMeta',
        parent=styles['Normal'],
        fontSize=8,
        spaceAfter=2,
        textColor=colors.black,
    )
    section_style = ParagraphStyle(
        'EcSection',
        parent=styles['Heading2'],
        fontSize=9.5,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.black,
    )
    cell_label_style = ParagraphStyle(
        'EcCellLabel',
        parent=meta_style,
        fontName='Helvetica-Bold',
        fontSize=7.5,
    )
    cell_value_style = ParagraphStyle(
        'EcCellValue',
        parent=meta_style,
        fontSize=7.5,
    )

    story = []
    logo = platypus_logo_findeco(ancho_mm=44, alto_mm=16)
    if logo is not None:
        story.extend([logo, Spacer(1, 3)])
    story.append(Paragraph('FINDECO — Estado financiero', title_style))
    story.append(
        Paragraph(
            (
                f"Préstamo <b>{datos.get('numero_prestamo', '')}</b> · "
                f"Estado: <b>{datos.get('estado_prestamo', '')}</b>"
            ),
            ParagraphStyle('EcSub', parent=meta_style, alignment=1),
        )
    )
    story.append(
        Paragraph(
            f"Emisión: {formato_fecha_hora_hn(timezone.localtime(timezone.now()))}",
            ParagraphStyle('EcDate', parent=meta_style, alignment=1),
        )
    )
    story.append(Spacer(1, 6))

    ficha = datos.get('ficha', {})
    ancho_ficha = TABLE_WIDTH_MM * mm / 4
    ficha_rows = [
        [
            Paragraph('Cliente:', cell_label_style),
            Paragraph(str(ficha.get('cliente', '—')), cell_value_style),
            Paragraph('Forma pago:', cell_label_style),
            Paragraph(str(ficha.get('forma_pago', '—')), cell_value_style),
        ],
        [
            Paragraph('Identidad:', cell_label_style),
            Paragraph(str(ficha.get('identidad', '—')), cell_value_style),
            Paragraph('Fecha entrega:', cell_label_style),
            Paragraph(_format_fecha(ficha.get('fecha_entrega')), cell_value_style),
        ],
        [
            Paragraph('Supervisor:', cell_label_style),
            Paragraph(str(ficha.get('supervisor', '—')), cell_value_style),
            Paragraph('Fecha vencimiento:', cell_label_style),
            Paragraph(_format_fecha(ficha.get('fecha_vencimiento')), cell_value_style),
        ],
        [
            Paragraph('Asesor:', cell_label_style),
            Paragraph(str(ficha.get('asesor', '—')), cell_value_style),
            Paragraph('Producto:', cell_label_style),
            Paragraph(str(ficha.get('producto', '—')), cell_value_style),
        ],
        [
            Paragraph('Garantía:', cell_label_style),
            Paragraph(str(ficha.get('garantia', '—')), cell_value_style),
            Paragraph('Interés planificado:', cell_label_style),
            Paragraph(_money_plain(ficha.get('interes_planificado', '0')), cell_value_style),
        ],
        [
            Paragraph('Ciclos:', cell_label_style),
            Paragraph(str(ficha.get('ciclos', '—')), cell_value_style),
            Paragraph('Tasa de interés:', cell_label_style),
            Paragraph(str(ficha.get('tasa_interes', '—')), cell_value_style),
        ],
        [
            Paragraph('Celular:', cell_label_style),
            Paragraph(str(ficha.get('telefono_celular', '—')), cell_value_style),
            Paragraph('Días mora:', cell_label_style),
            Paragraph(str(ficha.get('dias_mora', '0')), cell_value_style),
        ],
        [
            Paragraph('Monto desembolsado:', cell_label_style),
            Paragraph(_money_plain(ficha.get('monto_desembolsado', '0')), cell_value_style),
            Paragraph('Categoría:', cell_label_style),
            Paragraph(str(ficha.get('categoria', '—')), cell_value_style),
        ],
        [
            Paragraph('Forma desembolso:', cell_label_style),
            Paragraph(str(ficha.get('forma_desembolso', '—')), cell_value_style),
            Paragraph('Cartera:', cell_label_style),
            Paragraph(str(datos.get('cartera_nombre') or '—'), cell_value_style),
        ],
    ]
    if ficha.get('direccion'):
        ficha_rows.append(
            [
                Paragraph('Dirección:', cell_label_style),
                Paragraph(str(ficha.get('direccion')), cell_value_style),
                Paragraph('', cell_label_style),
                Paragraph('', cell_value_style),
            ]
        )

    tabla_ficha = Table(ficha_rows, colWidths=[ancho_ficha * 0.9, ancho_ficha * 1.3, ancho_ficha * 0.95, ancho_ficha * 1.25])
    tabla_ficha.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(tabla_ficha)

    resumen_saldos = datos.get('resumen_saldos', {})
    fecha_vencido = resumen_saldos.get('fecha_pago_vencido')
    col_vencido = 'Pago vencido'
    if fecha_vencido:
        col_vencido = f'Pago vencido al {_format_fecha(fecha_vencido)}'

    story.append(Paragraph('Resumen de saldos', section_style))
    saldos_data = [['', 'Saldo inicial', 'Abonos', 'Saldo actual', col_vencido]]
    for fila in resumen_saldos.get('filas', []):
        saldos_data.append(
            [
                fila.get('etiqueta', ''),
                _money_plain(fila.get('inicial', '0')),
                _money_plain(fila.get('abonos', '0')),
                _money_plain(fila.get('actual', '0')),
                _money_plain(fila.get('vencido', '0')),
            ]
        )
    ancho_tabla = TABLE_WIDTH_MM * mm
    saldos_widths = [ancho_tabla * 0.22, ancho_tabla * 0.195, ancho_tabla * 0.195, ancho_tabla * 0.195, ancho_tabla * 0.195]
    tabla_saldos = Table(saldos_data, colWidths=saldos_widths, repeatRows=1)
    estilo_saldos = _estilo_tabla_datos()
    total_row = len(saldos_data) - 1
    estilo_saldos.add('FONTNAME', (0, total_row), (-1, total_row), 'Helvetica-Bold')
    estilo_saldos.add('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    tabla_saldos.setStyle(estilo_saldos)
    story.append(tabla_saldos)

    def _tabla_seccion(
        titulo: str,
        headers: list[str],
        filas: list[list[str]],
        *,
        col_ratios: list[float],
        align_right_cols: list[int] | None = None,
        resaltar_ultima: bool = False,
    ) -> None:
        story.append(Paragraph(titulo, section_style))
        if not filas:
            story.append(Paragraph('Sin registros.', meta_style))
            return
        data = [headers] + filas
        total_ratio = sum(col_ratios)
        widths = [ancho_tabla * r / total_ratio for r in col_ratios]
        tabla = Table(data, colWidths=widths, repeatRows=1)
        estilo = _estilo_tabla_datos()
        estilo.add('ALIGN', (0, 1), (-1, -1), 'CENTER')
        for col in align_right_cols or []:
            estilo.add('ALIGN', (col, 0), (col, -1), 'RIGHT')
        if resaltar_ultima and len(data) > 1:
            last = len(data) - 1
            estilo.add('FONTNAME', (0, last), (-1, last), 'Helvetica-Bold')
            estilo.add('BACKGROUND', (0, last), (-1, last), colors.Color(0.94, 0.96, 0.98))
        tabla.setStyle(estilo)
        story.append(tabla)

    plan_filas = datos.get('plan_pagos') or datos.get('cuotas') or []
    plan_totales = datos.get('plan_pagos_totales') or {}
    plan_data = [
        [
            str(f.get('numero_cuota', '')),
            _format_fecha(f.get('fecha_programada')),
            _money_plain(f.get('capital_programado', '0')),
            _money_plain(f.get('interes_programado', '0')),
            _money_plain(f.get('total_programado', '0')),
            _money_plain(f.get('saldo_capital', '0')),
        ]
        for f in plan_filas
    ]
    if plan_data:
        plan_data.append(
            [
                'TOTAL',
                '—',
                _money_plain(plan_totales.get('capital', '0')),
                _money_plain(plan_totales.get('interes', '0')),
                _money_plain(plan_totales.get('total', '0')),
                _money_plain(plan_totales.get('saldo_capital', '0')),
            ]
        )
    _tabla_seccion(
        'Plan de pagos',
        ['N', 'Fecha programada', 'Capital', 'Interés', 'Total cuota + interés', 'Saldo capital'],
        plan_data,
        col_ratios=[8, 16, 16, 16, 22, 18],
        align_right_cols=[2, 3, 4, 5],
        resaltar_ultima=bool(plan_data),
    )

    abonos_filas = datos.get('abonos') or []
    abonos_totales = datos.get('abonos_totales') or {}
    abonos_data = [
        [
            str(f.get('n', '')),
            _format_fecha(f.get('fecha_pago')),
            str(f.get('documento') or '—'),
            _money_plain(f.get('capital', '0')),
            _money_plain(f.get('interes', '0')),
            _money_plain(f.get('total', '0')),
            _money_plain(f.get('saldo_capital', '0')),
        ]
        for f in abonos_filas
    ]
    if abonos_data:
        abonos_data.append(
            [
                'TOTAL',
                '—',
                'Abonado',
                _money_plain(abonos_totales.get('capital', '0')),
                _money_plain(abonos_totales.get('interes', '0')),
                _money_plain(abonos_totales.get('total', '0')),
                _money_plain(abonos_totales.get('saldo_capital', '0')),
            ]
        )
    _tabla_seccion(
        'Abonos',
        ['N', 'Fecha', 'Documento', 'Capital', 'Interés', 'Total', 'Saldo capital'],
        abonos_data,
        col_ratios=[7, 14, 18, 14, 14, 14, 16],
        align_right_cols=[3, 4, 5, 6],
        resaltar_ultima=bool(abonos_data),
    )

    historial_filas = datos.get('historial_prestamos') or []
    historial_data = [
        [
            str(f.get('prestamo') or '—'),
            _money_plain(f.get('monto', '0')),
            _money_plain(f.get('interes', '0')),
            str(f.get('plazo') if f.get('plazo') is not None else '—'),
            f"{f.get('tasa', '0')}%",
            str(f.get('producto') or '—'),
            _money_plain(f.get('saldo', '0')),
        ]
        for f in historial_filas
    ]
    _tabla_seccion(
        'Historial de préstamos',
        ['Préstamo', 'Monto', 'Interés', 'Plazo', 'Tasa', 'Producto', 'Saldo'],
        historial_data,
        col_ratios=[14, 14, 14, 10, 10, 18, 14],
        align_right_cols=[1, 2, 6],
    )

    doc.build(story)
    return buffer.getvalue()
