"""Exportación PDF del reporte trimestral regulatorio SAR (Honduras)."""

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

from .core.fechas_display import formato_fecha_hn, formato_fecha_hora_hn
from .core.findeco_brand import platypus_logo_findeco

MARGIN_H_MM = 16
TABLE_WIDTH_MM = (letter[0] / mm) - (2 * MARGIN_H_MM)

# Paleta formal (reporte regulatorio en blanco y negro)
_COLOR_NEGRO = colors.HexColor('#000000')
_COLOR_GRIS_OSCURO = colors.HexColor('#333333')
_COLOR_GRIS_MEDIO = colors.HexColor('#666666')
_COLOR_GRIS_CLARO = colors.HexColor('#f0f0f0')
_COLOR_GRIS_FILA = colors.HexColor('#fafafa')
_COLOR_BORDE = colors.HexColor('#000000')

_TRIMESTRE_NOMBRE = {
    1: 'Primer trimestre (enero – marzo)',
    2: 'Segundo trimestre (abril – junio)',
    3: 'Tercer trimestre (julio – septiembre)',
    4: 'Cuarto trimestre (octubre – diciembre)',
}

_LABEL_RANGO_MORA = {
    'hasta_30': '1 – 30 días',
    'de_31_a_60': '31 – 60 días',
    'de_61_a_90': '61 – 90 días',
    'mas_de_90': 'Más de 90 días',
}


def _money_pdf(value: str | Decimal | float | int) -> str:
    try:
        n = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return str(value)
    return f'L {n:,.2f}'


def _int_text(value: int | str) -> str:
    try:
        return f'{int(value):,}'
    except (TypeError, ValueError):
        return str(value)


def nombre_archivo_reporte_sar(trimestre: int, anio: int) -> str:
    return f'reporte-sar-T{trimestre}-{anio}.pdf'


def _fecha_display(valor: date | str | None) -> str:
    if valor is None:
        return '—'
    if isinstance(valor, str):
        try:
            valor = date.fromisoformat(valor)
        except ValueError:
            return valor
    return formato_fecha_hn(valor)


def exportar_reporte_sar_trimestral_pdf(datos: dict) -> bytes:
    """Genera PDF formal para informe trimestral de cartera (formato SAR Honduras)."""
    encabezado = datos.get('encabezado') or {}
    razon = (encabezado.get('nombre_entidad') or 'FINDECO').strip()
    rtn_emisor = (encabezado.get('rtn') or '').strip() or '—'
    direccion = (encabezado.get('direccion') or '').strip() or '—'
    telefono = (encabezado.get('telefono') or '').strip() or '—'
    correo = (encabezado.get('correo') or '').strip() or '—'

    trimestre = int(datos['trimestre'])
    anio = int(datos['anio'])
    operaciones = datos.get('detalle_operaciones') or {}
    vigente = datos.get('cartera_vigente', {})
    vencida = datos.get('cartera_vencida', {})
    ingresos = datos.get('ingresos') or {}
    resumen = datos.get('resumen') or {}
    mora_rangos = vencida.get('por_rango_dias') or {}
    total_prestamos_cartera = int(resumen.get('cartera_total_prestamos', 0))
    total_saldo_cartera = resumen.get('cartera_total_saldo', '0')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=MARGIN_H_MM * mm,
        rightMargin=MARGIN_H_MM * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f'Reporte SAR T{trimestre} {anio}',
    )
    styles = getSampleStyleSheet()
    sar_title = ParagraphStyle(
        'SarTitle',
        parent=styles['Heading1'],
        fontSize=14,
        alignment=1,
        spaceAfter=6,
        spaceBefore=4,
        textColor=_COLOR_NEGRO,
        fontName='Helvetica-Bold',
        leading=17,
    )
    sar_subtitle = ParagraphStyle(
        'SarSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        spaceAfter=3,
        textColor=_COLOR_GRIS_OSCURO,
        fontName='Helvetica-Bold',
        leading=13,
    )
    sar_subtitle_normal = ParagraphStyle(
        'SarSubtitleNormal',
        parent=sar_subtitle,
        fontName='Helvetica',
        fontSize=9,
        textColor=_COLOR_GRIS_MEDIO,
    )
    section = ParagraphStyle(
        'SarSection',
        parent=styles['Heading2'],
        fontSize=11,
        spaceBefore=12,
        spaceAfter=6,
        textColor=_COLOR_NEGRO,
        fontName='Helvetica-Bold',
        leading=14,
    )
    subsection = ParagraphStyle(
        'SarSubsection',
        parent=section,
        fontSize=10,
        spaceBefore=8,
        spaceAfter=4,
    )
    legal = ParagraphStyle(
        'SarLegal',
        parent=styles['Normal'],
        fontSize=9,
        textColor=_COLOR_GRIS_OSCURO,
        fontName='Helvetica',
        leading=12,
        spaceAfter=4,
    )

    story: list = []
    logo = platypus_logo_findeco(ancho_mm=45, alto_mm=16)
    if logo is not None:
        story.extend([logo, Spacer(1, 8)])

    story.extend(
        [
            Paragraph('REPÚBLICA DE HONDURAS', sar_subtitle),
            Paragraph('SERVICIO DE ADMINISTRACIÓN DE RENTAS (SAR)', sar_subtitle),
            Spacer(1, 10),
            Paragraph('INFORME TRIMESTRAL DE CARTERA Y OPERACIONES', sar_title),
            Paragraph(
                f'Periodo: {_TRIMESTRE_NOMBRE.get(trimestre, f"Trimestre {trimestre}")} — Año {anio}',
                sar_subtitle,
            ),
            Paragraph('Microfinanciera / contribuyente', sar_subtitle_normal),
            Spacer(1, 12),
        ]
    )

    periodo_tbl = Table(
        [
            ['Periodo fiscal', f'Año {anio}'],
            ['Trimestre', _TRIMESTRE_NOMBRE.get(trimestre, f'Trimestre {trimestre}')],
            [
                'Vigencia del informe',
                f'{_fecha_display(datos.get("fecha_inicio"))} al '
                f'{_fecha_display(datos.get("fecha_fin"))}',
            ],
        ],
        colWidths=[45 * mm, TABLE_WIDTH_MM * mm - 45 * mm],
    )
    periodo_tbl.setStyle(_estilo_tabla_etiquetas())
    story.extend([periodo_tbl, Spacer(1, 8)])

    story.append(Paragraph('I. Datos del contribuyente', section))
    contrib_tbl = Table(
        [
            ['Nombre de la entidad', razon],
            ['RTN', rtn_emisor],
            ['Trimestre / Año', f'T{trimestre} — {anio}'],
            ['Dirección', direccion],
            ['Teléfono', telefono],
            ['Correo', correo],
        ],
        colWidths=[40 * mm, TABLE_WIDTH_MM * mm - 40 * mm],
    )
    contrib_tbl.setStyle(_estilo_tabla_etiquetas())
    story.extend([contrib_tbl, Spacer(1, 6)])

    story.append(Paragraph('II. Detalle de operaciones (trimestre)', section))
    otorgados_tbl = Table(
        [
            ['Concepto', 'Valor'],
            [
                'Número de préstamos otorgados',
                _int_text(operaciones.get('total_prestamos_otorgados', 0)),
            ],
            [
                'Monto total de préstamos',
                _money_pdf(operaciones.get('monto_prestamos_otorgados', '0')),
            ],
            [
                'Tasa de interés promedio (%)',
                _decimal_pct(operaciones.get('tasa_interes_promedio')),
            ],
            [
                'Tasa de interés mínima / máxima (%)',
                f'{_decimal_pct(operaciones.get("tasa_interes_minima"))} / '
                f'{_decimal_pct(operaciones.get("tasa_interes_maxima"))}',
            ],
            [
                'Plazo promedio (cuotas)',
                _decimal_pct(operaciones.get('plazo_promedio')),
            ],
            [
                'Comisiones por desembolsos',
                _money_pdf(operaciones.get('comisiones_desembolsadas', '0')),
            ],
        ],
        colWidths=[95 * mm, TABLE_WIDTH_MM * mm - 95 * mm],
    )
    otorgados_tbl.setStyle(_estilo_tabla_datos())
    story.extend([otorgados_tbl, Spacer(1, 6)])

    story.append(Paragraph('III. Posición de cartera al cierre del trimestre', section))
    cartera_tbl = Table(
        [
            ['Concepto', 'N.º préstamos', 'Saldo pendiente (L)'],
            [
                'Cartera vigente',
                _int_text(vigente.get('prestamos', 0)),
                _money_pdf(vigente.get('saldo', '0')),
            ],
            [
                'Cartera vencida (mora)',
                _int_text(vencida.get('prestamos', 0)),
                _money_pdf(vencida.get('saldo', '0')),
            ],
            [
                'Total cartera',
                _int_text(total_prestamos_cartera),
                _money_pdf(total_saldo_cartera),
            ],
        ],
        colWidths=[80 * mm, 35 * mm, TABLE_WIDTH_MM * mm - 115 * mm],
    )
    cartera_style = _estilo_tabla_datos()
    cartera_style.add('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold')
    cartera_style.add('BACKGROUND', (0, 3), (-1, 3), _COLOR_GRIS_CLARO)
    cartera_tbl.setStyle(cartera_style)
    story.extend([cartera_tbl, Spacer(1, 6)])

    mora_rows = [
        ['Rango días mora', 'N.º préstamos', 'Saldo (L)'],
    ]
    for clave, etiqueta in _LABEL_RANGO_MORA.items():
        bloque = mora_rangos.get(clave, {})
        mora_rows.append(
            [
                etiqueta,
                _int_text(bloque.get('prestamos', 0)),
                _money_pdf(bloque.get('saldo', '0')),
            ]
        )
    mora_tbl = Table(
        mora_rows,
        colWidths=[55 * mm, 35 * mm, TABLE_WIDTH_MM * mm - 90 * mm],
    )
    mora_tbl.setStyle(_estilo_tabla_datos())
    story.extend(
        [
            Paragraph('Cartera vencida por antigüedad de mora', subsection),
            mora_tbl,
            Spacer(1, 6),
        ]
    )

    story.append(Paragraph('IV. Ingresos del trimestre', section))
    ingresos_tbl = Table(
        [
            ['Concepto', 'Monto (Lempiras)'],
            [
                'Intereses generados / cobrados',
                _money_pdf(ingresos.get('intereses_generados', '0')),
            ],
            [
                'Comisiones cobradas (desembolsos)',
                _money_pdf(ingresos.get('comisiones_cobradas', '0')),
            ],
            [
                'Pagos recibidos (total)',
                _money_pdf(ingresos.get('pagos_recibidos', '0')),
            ],
            [
                'Total abonos a capital',
                _money_pdf(ingresos.get('total_abonos_capital', '0')),
            ],
            [
                'Total intereses pagados',
                _money_pdf(ingresos.get('total_intereses_pagados', '0')),
            ],
            [
                'Total mora pagada',
                _money_pdf(ingresos.get('total_mora_pagada', '0')),
            ],
        ],
        colWidths=[100 * mm, TABLE_WIDTH_MM * mm - 100 * mm],
    )
    ingresos_tbl.setStyle(_estilo_tabla_datos())
    story.extend([ingresos_tbl, Spacer(1, 6)])

    story.append(Paragraph('V. Resumen', section))
    resumen_tbl = Table(
        [
            ['Concepto', 'Valor'],
            [
                'Cartera total (vigente + vencida)',
                f'{_int_text(total_prestamos_cartera)} préstamos — '
                f'{_money_pdf(total_saldo_cartera)}',
            ],
            [
                'Indicador de morosidad',
                f'{_decimal_pct(resumen.get("porcentaje_morosidad"))}% del saldo en cartera vencida',
            ],
        ],
        colWidths=[95 * mm, TABLE_WIDTH_MM * mm - 95 * mm],
    )
    resumen_tbl.setStyle(_estilo_tabla_datos())
    story.extend([resumen_tbl, Spacer(1, 12)])

    story.append(
        Paragraph(
            (
                'Declaro bajo fe de juramento que la información consignada en este informe '
                'corresponde fielmente a las operaciones registradas en el periodo indicado, '
                'conforme a los registros contables y operativos de la entidad.'
            ),
            legal,
        )
    )
    story.append(Spacer(1, 16))

    firmas_tbl = Table(
        [
            ['_____________________________', '_____________________________'],
            ['Nombre y firma — Elaborado por', 'Nombre y firma — Representante legal'],
            ['', ''],
            ['_____________________________', ''],
            ['Fecha', ''],
        ],
        colWidths=[TABLE_WIDTH_MM * mm / 2, TABLE_WIDTH_MM * mm / 2],
    )
    firmas_tbl.setStyle(
        TableStyle(
            [
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTNAME', (0, 4), (0, 4), 'Helvetica-Bold'),
                ('TEXTCOLOR', (0, 0), (-1, -1), _COLOR_NEGRO),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([firmas_tbl, Spacer(1, 10)])

    story.append(
        Paragraph(
            (
                f'Documento generado electrónicamente el '
                f'{formato_fecha_hora_hn(timezone.localtime(timezone.now()))}. '
                'Uso interno y presentación ante autoridades competentes según normativa vigente.'
            ),
            ParagraphStyle(
                'SarFooter',
                parent=legal,
                alignment=1,
                fontSize=8,
                textColor=_COLOR_GRIS_MEDIO,
            ),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _decimal_pct(value: str | Decimal | float | int | None) -> str:
    if value is None or value == '':
        return '0.00'
    try:
        return f'{Decimal(str(value)):.2f}'
    except (ArithmeticError, ValueError):
        return str(value)


def _estilo_tabla_etiquetas() -> TableStyle:
    """Tablas clave-valor (encabezado, contribuyente)."""
    return TableStyle(
        [
            ('BACKGROUND', (0, 0), (0, -1), _COLOR_GRIS_CLARO),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('TEXTCOLOR', (0, 0), (-1, -1), _COLOR_NEGRO),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.75, _COLOR_BORDE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]
    )


def _estilo_tabla_datos() -> TableStyle:
    """Tablas de datos: encabezado negro sobre gris, cuerpo formal."""
    return TableStyle(
        [
            ('BACKGROUND', (0, 0), (-1, 0), _COLOR_GRIS_CLARO),
            ('TEXTCOLOR', (0, 0), (-1, 0), _COLOR_NEGRO),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('TEXTCOLOR', (0, 1), (-1, -1), _COLOR_NEGRO),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.75, _COLOR_BORDE),
            ('LINEBELOW', (0, 0), (-1, 0), 1.25, _COLOR_BORDE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _COLOR_GRIS_FILA]),
        ]
    )
