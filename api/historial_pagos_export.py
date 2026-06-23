"""Exportación Excel y PDF del historial de pagos cobrados."""

from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .core.findeco_brand import platypus_logo_findeco

MESES_ES = (
    'Enero',
    'Febrero',
    'Marzo',
    'Abril',
    'Mayo',
    'Junio',
    'Julio',
    'Agosto',
    'Septiembre',
    'Octubre',
    'Noviembre',
    'Diciembre',
)

COLUMNAS_EXCEL = (
    ('fecha_pago', 'Fecha'),
    ('nombre_cliente', 'Cliente'),
    ('dni_cliente', 'DNI'),
    ('numero_prestamo', 'Préstamo'),
    ('cartera_nombre', 'Cartera'),
    ('documento', 'Documento'),
    ('capital', 'Capital'),
    ('interes', 'Interés'),
    ('mora', 'Mora'),
    ('total', 'Total'),
)


def _periodo_legible(datos: dict) -> str:
    modo = datos.get('modo', 'dia')
    inicio = datos.get('fecha_inicio', '')
    fin = datos.get('fecha_fin', '')
    if modo == 'dia' and inicio:
        return inicio
    if modo == 'mes' and inicio:
        try:
            y, m, _ = inicio.split('-')
            return f'{MESES_ES[int(m) - 1]} {y}'
        except (ValueError, IndexError):
            return f'{inicio} – {fin}'
    if modo == 'anio' and inicio:
        return inicio[:4]
    if inicio == fin:
        return inicio or '—'
    return f'{inicio} – {fin}'


def nombre_archivo_historial(datos: dict, extension: str) -> str:
    periodo = _periodo_legible(datos).replace(' ', '_').replace('–', '-')
    cartera = (datos.get('cartera_etiqueta') or 'todas').replace(' ', '_')
    return f'historial_pagos_{cartera}_{periodo}.{extension}'


def exportar_historial_pagos_xlsx(datos: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Historial pagos'

    header_fill = PatternFill('solid', fgColor='1F4E79')
    header_font = Font(bold=True, color='FFFFFF')

    ws.append(['FINDECO — Historial de pagos'])
    ws.append([f"Cartera: {datos.get('cartera_etiqueta', 'Todas')}"])
    ws.append([f"Periodo: {_periodo_legible(datos)}"])
    ws.append([])

    headers = [label for _, label in COLUMNAS_EXCEL]
    ws.append(headers)
    header_row = ws.max_row
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.fill = header_fill
        cell.font = header_font

    for fila in datos.get('filas', []):
        ws.append([fila.get(key, '') for key, _ in COLUMNAS_EXCEL])

    resumen = datos.get('resumen', {})
    ws.append([])
    ws.append(
        [
            'Totales',
            '',
            '',
            '',
            '',
            '',
            resumen.get('total_capital', '0'),
            resumen.get('total_interes', '0'),
            resumen.get('total_mora', '0'),
            resumen.get('total_cobrado', '0'),
        ]
    )
    ws.append(['Registros', resumen.get('registros', 0)])

    for col in ws.columns:
        max_len = 0
        letter_col = col[0].column_letter
        for cell in col:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[letter_col].width = min(max(max_len + 2, 10), 40)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _money_pdf(value: str | Decimal) -> str:
    try:
        n = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return str(value)
    return f'L {n:,.2f}'


def exportar_historial_pagos_pdf(datos: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'HistTitle',
        parent=styles['Heading1'],
        fontSize=14,
        alignment=1,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        'HistMeta',
        parent=styles['Normal'],
        fontSize=9,
        alignment=1,
        spaceAfter=2,
    )

    story = []
    logo = platypus_logo_findeco(ancho_mm=52, alto_mm=20)
    if logo is not None:
        story.extend([logo, Spacer(1, 4)])
    story.extend(
        [
            Paragraph('FINDECO — Historial de pagos', title_style),
            Paragraph(f"Cartera: {datos.get('cartera_etiqueta', 'Todas')}", meta_style),
            Paragraph(f"Periodo: {_periodo_legible(datos)}", meta_style),
            Spacer(1, 8),
        ]
    )

    table_data = [
        ['Fecha', 'Cliente', 'DNI', 'Préstamo', 'Cartera', 'Doc.', 'Capital', 'Interés', 'Mora', 'Total'],
    ]
    for fila in datos.get('filas', []):
        table_data.append(
            [
                fila.get('fecha_pago', ''),
                fila.get('nombre_cliente', ''),
                fila.get('dni_cliente', ''),
                fila.get('numero_prestamo', ''),
                fila.get('cartera_nombre', ''),
                fila.get('documento') or '—',
                _money_pdf(fila.get('capital', '0')),
                _money_pdf(fila.get('interes', '0')),
                _money_pdf(fila.get('mora', '0')),
                _money_pdf(fila.get('total', '0')),
            ]
        )

    resumen = datos.get('resumen', {})
    table_data.append(
        [
            'TOTALES',
            '',
            '',
            '',
            '',
            f"{resumen.get('registros', 0)} reg.",
            _money_pdf(resumen.get('total_capital', '0')),
            _money_pdf(resumen.get('total_interes', '0')),
            _money_pdf(resumen.get('total_mora', '0')),
            _money_pdf(resumen.get('total_cobrado', '0')),
        ]
    )

    col_widths = [22 * mm, 38 * mm, 24 * mm, 26 * mm, 28 * mm, 22 * mm, 22 * mm, 22 * mm, 18 * mm, 24 * mm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E79')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('ALIGN', (6, 0), (-1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8EEF4')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F7F9FC')]),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
