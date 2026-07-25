"""Exportación PDF de la hoja de cobros (cartera completa)."""

from __future__ import annotations

import io
import re
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils.dateparse import parse_date, parse_datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .core.fechas_display import formato_fecha_hn, formato_fecha_hora_hn
from .core.findeco_brand import platypus_logo_findeco

DIAS_ES = (
    'LUNES',
    'MARTES',
    'MIÉRCOLES',
    'JUEVES',
    'VIERNES',
    'SÁBADO',
    'DOMINGO',
)
MESES_ES = (
    'ENERO',
    'FEBRERO',
    'MARZO',
    'ABRIL',
    'MAYO',
    'JUNIO',
    'JULIO',
    'AGOSTO',
    'SEPTIEMBRE',
    'OCTUBRE',
    'NOVIEMBRE',
    'DICIEMBRE',
)


def _money(value: str | Decimal | None) -> str:
    if value in (None, ''):
        return ''
    try:
        n = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return str(value)
    return f'{n:,.2f}'


def _fecha_celda(iso: str | None) -> str:
    if not iso:
        return ''
    parsed = parse_date(str(iso)[:10])
    if parsed is None:
        return str(iso)
    return formato_fecha_hn(parsed)


def _fecha_reporte_legible(iso: str | None) -> str:
    if not iso:
        return '—'
    parsed = parse_date(str(iso)[:10])
    if parsed is None:
        return str(iso).upper()
    dia = parsed.strftime('%d')
    return f'{DIAS_ES[parsed.weekday()]} {dia} DE {MESES_ES[parsed.month - 1]} {parsed.year}'


def _generado_legible(iso: str | None) -> str:
    if not iso:
        return '—'
    dt = parse_datetime(iso)
    if dt is None:
        return str(iso)
    return formato_fecha_hora_hn(dt)


def _slug_archivo(texto: str) -> str:
    limpio = re.sub(r'[^\w\-]+', '_', (texto or 'cartera').strip(), flags=re.UNICODE)
    return limpio.strip('_') or 'cartera'


def nombre_archivo_hoja_cobros(datos: dict) -> str:
    cartera = _slug_archivo(str(datos.get('cartera_etiqueta') or 'cartera'))
    fecha = (datos.get('fecha_reporte') or 'hoy').replace('-', '')
    return f'hoja_cobros_{cartera}_{fecha}.pdf'


def _parrafo(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape((text or '').strip() or ' '), style)


ESTADO_LABELS = {
    'activo': 'Activo',
    'pendiente_aprobacion': 'Pendiente',
    'pagado': 'Pagado',
    'mora': 'Mora',
    'cancelado': 'Cancelado',
}


def _estado_label(estado: str | None) -> str:
    clave = (estado or '').strip()
    return ESTADO_LABELS.get(clave, clave or '—')


def _texto_cuota_pendiente(fila: dict) -> str:
    base = _money(fila.get('cuota_siguiente_monto')) or '—'
    n = int(fila.get('cuotas_atrasadas') or 0)
    if n <= 0:
        return base
    nums = (fila.get('cuotas_atrasadas_numeros') or '').strip()
    if nums:
        nums_fmt = ', #'.join(part.strip() for part in nums.split(',') if part.strip())
        extra = f'{n} atrasada{"s" if n != 1 else ""} (#{nums_fmt})'
    else:
        extra = f'{n} atrasada{"s" if n != 1 else ""}'
    return f'{base}<br/><font color="#b91c1c" size="6">{escape(extra)}</font>'


def exportar_hoja_cobros_seguimiento_pdf(datos: dict) -> bytes:
    """PDF compacto: préstamo, cliente, estado, cuota y cobrado hoy (vacío si no cobró)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle(
        'SegMeta',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        spaceAfter=2,
        fontName='Helvetica-Bold',
    )
    cell_style = ParagraphStyle(
        'SegCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        wordWrap='CJK',
    )
    cell_right = ParagraphStyle(
        'SegCellRight',
        parent=cell_style,
        alignment=2,
    )
    header_style = ParagraphStyle(
        'SegHeader',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        alignment=1,
        fontName='Helvetica-Bold',
        textColor=colors.black,
    )

    story = []
    logo = platypus_logo_findeco(ancho_mm=48, alto_mm=18)
    if logo is not None:
        story.extend([logo, Spacer(1, 4)])
    story.extend(
        [
            Paragraph(f"CARTERA: {datos.get('cartera_etiqueta', '—')}", meta_style),
            Paragraph(f"FECHA: {_fecha_reporte_legible(datos.get('fecha_reporte'))}", meta_style),
            Paragraph(f"GENERADO: {_generado_legible(datos.get('generado_en'))}", meta_style),
            Spacer(1, 8),
        ]
    )

    headers = ['N', 'Nº PRÉSTAMO', 'NOMBRE CLIENTE', 'ESTADO', 'CUOTA', 'COBRADO']
    col_widths = [10 * mm, 28 * mm, 62 * mm, 28 * mm, 28 * mm, 28 * mm]

    table_data = [[_parrafo(h, header_style) for h in headers]]
    filas = list(datos.get('filas') or [])
    total_cobrado = Decimal('0.00')
    cobrados = 0
    for idx, fila in enumerate(filas, start=1):
        monto_hoy = fila.get('monto_cobrado_hoy') or ''
        if fila.get('cobrado_hoy') and monto_hoy not in (None, ''):
            try:
                total_cobrado += Decimal(str(monto_hoy))
                cobrados += 1
            except (ArithmeticError, ValueError):
                pass
        n_cuota = fila.get('cuota_siguiente_numero')
        monto_cuota = fila.get('cuota_siguiente_monto') or fila.get('cuota')
        if n_cuota:
            cuota_txt = f'#{n_cuota}  {_money(monto_cuota)}'
        else:
            cuota_txt = _money(monto_cuota) or '—'
        table_data.append(
            [
                str(idx),
                str(fila.get('numero_prestamo') or ''),
                _parrafo(str(fila.get('nombre_cliente') or ''), cell_style),
                _parrafo(_estado_label(fila.get('estado')), cell_style),
                _parrafo(cuota_txt, cell_right),
                _parrafo(_money(monto_hoy) if monto_hoy not in (None, '') else '', cell_right),
            ]
        )

    if not filas:
        table_data.append(
            [
                '',
                '',
                _parrafo('Sin préstamos en esta cartera.', cell_style),
                '',
                '',
                '',
            ]
        )

    table_data.append(
        [
            '',
            '',
            _parrafo(f'TOTALES ({cobrados} cobrado(s) de {len(filas)}):', cell_right),
            '',
            '',
            _parrafo(_money(total_cobrado) if total_cobrado else '', cell_right),
        ]
    )

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FAFAFA')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#FAFAFA')]),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _texto_cuota_fila(fila: dict) -> str:
    n_cuota = fila.get('cuota_siguiente_numero')
    monto_cuota = fila.get('cuota_siguiente_monto') or fila.get('cuota')
    if n_cuota:
        return f'#{n_cuota}  {_money(monto_cuota)}'
    return _money(monto_cuota) or '—'


def exportar_hoja_cobros_listado_pdf(datos: dict) -> bytes:
    """PDF simple: préstamo, cliente, estado, cuota y columna en blanco."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle(
        'ListMeta',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        spaceAfter=2,
        fontName='Helvetica-Bold',
    )
    cell_style = ParagraphStyle(
        'ListCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        wordWrap='CJK',
    )
    cell_right = ParagraphStyle(
        'ListCellRight',
        parent=cell_style,
        alignment=2,
    )
    header_style = ParagraphStyle(
        'ListHeader',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        alignment=1,
        fontName='Helvetica-Bold',
        textColor=colors.black,
    )

    story = []
    logo = platypus_logo_findeco(ancho_mm=48, alto_mm=18)
    if logo is not None:
        story.extend([logo, Spacer(1, 4)])
    story.extend(
        [
            Paragraph(f"CARTERA: {datos.get('cartera_etiqueta', '—')}", meta_style),
            Paragraph(f"FECHA: {_fecha_reporte_legible(datos.get('fecha_reporte'))}", meta_style),
            Paragraph(f"GENERADO: {_generado_legible(datos.get('generado_en'))}", meta_style),
            Spacer(1, 8),
        ]
    )

    headers = ['N', 'Nº PRÉSTAMO', 'NOMBRE CLIENTE', 'ESTADO', 'CUOTA', 'ESPACIO']
    col_widths = [10 * mm, 28 * mm, 62 * mm, 28 * mm, 30 * mm, 32 * mm]

    table_data = [[_parrafo(h, header_style) for h in headers]]
    filas = list(datos.get('filas') or [])
    total_cuota = Decimal('0.00')
    for idx, fila in enumerate(filas, start=1):
        monto_cuota = fila.get('cuota_siguiente_monto') or fila.get('cuota')
        try:
            if monto_cuota not in (None, ''):
                total_cuota += Decimal(str(monto_cuota))
        except (ArithmeticError, ValueError):
            pass
        table_data.append(
            [
                str(idx),
                str(fila.get('numero_prestamo') or ''),
                _parrafo(str(fila.get('nombre_cliente') or ''), cell_style),
                _parrafo(_estado_label(fila.get('estado')), cell_style),
                _parrafo(_texto_cuota_fila(fila), cell_right),
                '',
            ]
        )

    if not filas:
        table_data.append(
            [
                '',
                '',
                _parrafo('Sin préstamos en esta cartera.', cell_style),
                '',
                '',
                '',
            ]
        )

    table_data.append(
        [
            '',
            '',
            _parrafo(f'TOTALES ({len(filas)}):', cell_right),
            '',
            _parrafo(_money(total_cuota) if total_cuota else '', cell_right),
            '',
        ]
    )

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('ALIGN', (4, 1), (4, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FAFAFA')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#FAFAFA')]),
                ('BACKGROUND', (5, 1), (5, -2), colors.white),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def exportar_hoja_cobros_pdf(datos: dict) -> bytes:
    """PDF landscape con el listado completo de la hoja de cobros + columnas en blanco."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle(
        'HojaMeta',
        parent=styles['Normal'],
        fontSize=9,
        alignment=1,
        spaceAfter=2,
        fontName='Helvetica-Bold',
    )
    cell_style = ParagraphStyle(
        'HojaCell',
        parent=styles['Normal'],
        fontSize=6.5,
        leading=8,
        wordWrap='CJK',
    )
    cell_right = ParagraphStyle(
        'HojaCellRight',
        parent=cell_style,
        alignment=2,
    )
    header_style = ParagraphStyle(
        'HojaHeader',
        parent=styles['Normal'],
        fontSize=6.5,
        leading=8,
        alignment=1,
        fontName='Helvetica-Bold',
        textColor=colors.black,
    )

    story = []
    logo = platypus_logo_findeco(ancho_mm=52, alto_mm=20)
    if logo is not None:
        story.extend([logo, Spacer(1, 3)])
    story.extend(
        [
            Paragraph(f"CARTERA: {datos.get('cartera_etiqueta', '—')}", meta_style),
            Paragraph(f"FECHA: {_fecha_reporte_legible(datos.get('fecha_reporte'))}", meta_style),
            Paragraph(f"GENERADO: {_generado_legible(datos.get('generado_en'))}", meta_style),
            Spacer(1, 6),
        ]
    )

    headers = [
        'N',
        'NOMBRE CLIENTE',
        'ENTREGA',
        'VENCE',
        'SALDO INICIAL',
        'CUOTA',
        'CUOTA PEND.',
        'SALDO ACTUAL',
        'Nº PRESTAMO',
        'CELULAR',
        'ABONO DE CUOTAS',
        'ESPACIO',
    ]
    col_widths = [
        8 * mm,
        42 * mm,
        18 * mm,
        18 * mm,
        22 * mm,
        18 * mm,
        24 * mm,
        22 * mm,
        18 * mm,
        20 * mm,
        24 * mm,
        22 * mm,
    ]

    table_data = [[_parrafo(h, header_style) for h in headers]]
    filas = list(datos.get('filas') or [])
    for idx, fila in enumerate(filas, start=1):
        table_data.append(
            [
                str(idx),
                _parrafo(str(fila.get('nombre_cliente') or ''), cell_style),
                _fecha_celda(fila.get('fecha_entrega')),
                _fecha_celda(fila.get('fecha_vencimiento')),
                _parrafo(_money(fila.get('saldo_inicial')), cell_right),
                _parrafo(_money(fila.get('cuota')), cell_right),
                Paragraph(_texto_cuota_pendiente(fila), cell_right),
                _parrafo(_money(fila.get('saldo_actual')), cell_right),
                str(fila.get('numero_prestamo') or ''),
                str((fila.get('telefono') or '').strip()),
                '',
                '',
            ]
        )

    resumen = datos.get('resumen') or {}
    table_data.append(
        [
            '',
            '',
            '',
            _parrafo('TOTALES:', cell_right),
            _parrafo(_money(resumen.get('total_saldo_inicial')), cell_right),
            _parrafo(_money(resumen.get('total_cuota')), cell_right),
            '',
            _parrafo(_money(resumen.get('total_saldo_actual')), cell_right),
            '',
            '',
            '',
            '',
        ]
    )

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 6.5),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (3, -1), 'CENTER'),
                ('ALIGN', (8, 0), (9, -1), 'CENTER'),
                ('ALIGN', (4, 1), (7, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FAFAFA')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#FAFAFA')]),
                ('BACKGROUND', (10, 1), (11, -2), colors.white),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
