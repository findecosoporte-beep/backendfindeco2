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
from .core.distribucion_pago import cuotas_cubiertas_por_pago_acumulado, total_abonado_prestamo
from .core.fechas_display import ahora_local_iso, cobrado_en_efectivo, formato_fecha_hn, formato_fecha_hora_hn, formato_hora_hn
from .core.findeco_brand import platypus_logo_findeco
from .core.money import round_money
from .core.reporte_saldos import monto_cuota_programada
from .models import Pago, Prestamo, PrestamoCuota

ETIQUETAS_ESTADO_PRESTAMO = {
    'pendiente_aprobacion': 'Pendiente aprobación',
    'activo': 'Activo',
    'pagado': 'Pagado',
    'mora': 'Mora',
    'cancelado': 'Cancelado',
}

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


def pago_por_cuota_con_fallback(cuotas: list[PrestamoCuota], pagos_ordenados: list[Pago]) -> dict[int, Pago]:
    """Asigna pagos a cuotas por documento o, en su defecto, por orden cronológico."""
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

    # Cuotas cubiertas por el acumulado total pagado (aunque el excedente haya
    # quedado como abono a capital y no como "Cuota N" de cada una): el cliente
    # pudo adelantar varias cuotas de una sola vez, con o sin liquidar todo el plan.
    abonado_total = total_abonado_prestamo(pagos)
    cubiertas_por_acumulado = cuotas_cubiertas_por_pago_acumulado(cuotas, abonado_total)
    ultimo_pago = pagos[-1] if pagos else None

    filas_cuotas = []
    for cuota in cuotas:
        pago = pago_map.get(cuota.numero_cuota)
        if pago is not None:
            estado = 'Pagada'
            fecha_pago_val = pago.fecha_pago.isoformat()
            hora_val = formato_hora_hn(cobrado_en_efectivo(pago))
            documento_val = pago.documento or f'Cuota {cuota.numero_cuota}'
        elif cuota.numero_cuota in cubiertas_por_acumulado and ultimo_pago is not None:
            estado = 'Pagada'
            fecha_pago_val = ultimo_pago.fecha_pago.isoformat()
            hora_val = formato_hora_hn(cobrado_en_efectivo(ultimo_pago))
            documento_val = 'Cubierta por abono a capital'
        else:
            estado = 'Pendiente'
            fecha_pago_val = ''
            hora_val = ''
            documento_val = ''
        filas_cuotas.append(
            {
                'numero_cuota': cuota.numero_cuota,
                'fecha_programada': cuota.fecha_programada.isoformat(),
                'total_programado': str(round_money(monto_cuota_programada(cuota))),
                'saldo_capital': str(round_money(cuota.saldo_capital_programado)),
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

    return {
        'numero_prestamo': prestamo.numero_prestamo,
        'nombre_cliente': cliente.nombre if cliente else '',
        'dni_cliente': (cliente.dni if cliente else '') or '',
        'telefono_cliente': ((cliente.telefono if cliente else '') or '').strip(),
        'cartera_nombre': (cartera.nombre if cartera else '') or '',
        'estado_prestamo': ETIQUETAS_ESTADO_PRESTAMO.get(prestamo.estado, prestamo.estado),
        'fecha_emision': ahora_local_iso(),
        'cuotas': filas_cuotas,
        'resumen': {
            'cuotas_pagadas': sum(1 for f in filas_cuotas if f['estado'] == 'Pagada'),
            'cuotas_pendientes': sum(1 for f in filas_cuotas if f['estado'] == 'Pendiente'),
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
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'EcTitle',
        parent=styles['Heading1'],
        fontSize=14,
        alignment=1,
        spaceAfter=6,
        textColor=colors.black,
    )
    meta_style = ParagraphStyle(
        'EcMeta',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=2,
        textColor=colors.black,
    )
    section_style = ParagraphStyle(
        'EcSection',
        parent=styles['Heading2'],
        fontSize=10,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.black,
    )

    story = []
    logo = platypus_logo_findeco(ancho_mm=48, alto_mm=18)
    if logo is not None:
        story.extend([logo, Spacer(1, 4)])
    story.append(Paragraph('FINDECO — Estado de cuenta', title_style))
    story.append(
        Paragraph(
            f"Emisión: {formato_fecha_hora_hn(timezone.localtime(timezone.now()))}",
            ParagraphStyle('EcDate', parent=meta_style, alignment=1),
        )
    )
    story.append(Spacer(1, 8))

    meta_lines = [
        f"<b>Cliente:</b> {datos.get('nombre_cliente', '')}",
        f"<b>DNI:</b> {datos.get('dni_cliente', '—')}",
        f"<b>Teléfono:</b> {datos.get('telefono_cliente') or '—'}",
        f"<b>Préstamo:</b> {datos.get('numero_prestamo', '')}",
        f"<b>Cartera:</b> {datos.get('cartera_nombre') or '—'}",
        f"<b>Estado:</b> {datos.get('estado_prestamo', '')}",
    ]
    for line in meta_lines:
        story.append(Paragraph(line, meta_style))

    resumen = datos.get('resumen', {})
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            (
                f"<b>Cuotas pagadas:</b> {resumen.get('cuotas_pagadas', 0)} · "
                f"<b>Pendientes:</b> {resumen.get('cuotas_pendientes', 0)} · "
                f"<b>Cobros:</b> {resumen.get('total_pagos', 0)} · "
                f"<b>Total abonado:</b> {_money_pdf(resumen.get('total_abonado', '0'))}"
            ),
            meta_style,
        )
    )
    story.append(
        Paragraph(
            (
                f"Capital: {_money_pdf(resumen.get('total_capital', '0'))} · "
                f"Interés: {_money_pdf(resumen.get('total_interes', '0'))}"
            ),
            meta_style,
        )
    )

    story.append(Paragraph('Plan de cuotas', section_style))
    table_data = [
        ['N°', 'Fecha programada', 'Cuota', 'Saldo cap.', 'Estado', 'Fecha canceló', 'Hora'],
    ]
    for fila in datos.get('cuotas', []):
        table_data.append(
            [
                str(fila.get('numero_cuota', '')),
                _format_fecha(fila.get('fecha_programada')),
                _money_pdf(fila.get('total_programado', '0')),
                _money_pdf(fila.get('saldo_capital', '0')),
                fila.get('estado', ''),
                _format_fecha(fila.get('fecha_cancelo') or fila.get('fecha_pago') or None),
                fila.get('hora_pago') or '—',
            ]
        )

    col_widths = _anchos_tabla_plan_cuotas()
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.black),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (2, 0), (3, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
