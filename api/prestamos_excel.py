"""Exportación de préstamos a Excel (.xlsx) sin colores."""

from __future__ import annotations

import io
from collections.abc import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font

from .models import Prestamo

ESTADO_LABELS = {
    'activo': 'Activo',
    'pendiente_aprobacion': 'Pendiente aprobación',
    'pagado': 'Pagado',
    'mora': 'Mora',
    'cancelado': 'Cancelado',
}

FORMA_PAGO_LABELS = {
    'semanal': 'Semanal',
    'mensual': 'Mensual',
    'quincenal': 'Quincenal',
}

COLUMNAS: tuple[tuple[str, str], ...] = (
    ('codigo_prestamo', 'Código préstamo'),
    ('numero_prestamo', 'Nº préstamo'),
    ('cliente', 'Cliente'),
    ('dni_cliente', 'DNI cliente'),
    ('cartera', 'Cartera'),
    ('zona', 'Zona'),
    ('producto', 'Producto'),
    ('monto', 'Monto'),
    ('tasa_interes', 'Tasa %'),
    ('plazo', 'Plazo'),
    ('forma_pago', 'Forma de pago'),
    ('estado', 'Estado'),
    ('dias_mora', 'Días mora'),
    ('fecha_entrega', 'Fecha entrega'),
    ('fecha_vencimiento', 'Fecha vencimiento'),
    ('asesor', 'Asesor'),
    ('sucursal', 'Sucursal'),
    ('creado_en', 'Registrado'),
    ('creado_por', 'Registrado por'),
    ('actualizado_en', 'Modificado'),
    ('modificado_por', 'Modificado por'),
)


def _texto(valor) -> str:
    if valor is None:
        return ''
    return str(valor).strip()


def _fila_prestamo(prestamo: Prestamo) -> list:
    cliente = prestamo.id_cliente
    cartera = prestamo.id_cartera
    zona = prestamo.id_zona
    return [
        _texto(prestamo.codigo_prestamo) or _texto(prestamo.numero_prestamo) or str(prestamo.id_prestamo),
        _texto(prestamo.numero_prestamo) or str(prestamo.id_prestamo),
        _texto(cliente.nombre) if cliente else '',
        _texto(cliente.dni) if cliente else '',
        _texto(cartera.nombre) if cartera else '',
        _texto(zona.nombre) if zona else '',
        _texto(prestamo.producto),
        float(prestamo.monto) if prestamo.monto is not None else '',
        float(prestamo.tasa_interes) if prestamo.tasa_interes is not None else '',
        prestamo.plazo if prestamo.plazo is not None else '',
        FORMA_PAGO_LABELS.get(prestamo.forma_pago or '', prestamo.forma_pago or ''),
        ESTADO_LABELS.get(prestamo.estado or '', prestamo.estado or ''),
        prestamo.dias_mora if prestamo.dias_mora is not None else 0,
        prestamo.fecha_entrega.isoformat() if prestamo.fecha_entrega else '',
        prestamo.fecha_vencimiento.isoformat() if prestamo.fecha_vencimiento else '',
        _texto(prestamo.asesor),
        _texto(prestamo.sucursal),
        prestamo.creado_en.isoformat(sep=' ', timespec='minutes') if prestamo.creado_en else '',
        _texto(prestamo.creado_por.nombre) if prestamo.creado_por_id else '',
        (
            prestamo.actualizado_en.isoformat(sep=' ', timespec='minutes')
            if prestamo.actualizado_en
            else ''
        ),
        _texto(prestamo.modificado_por.nombre) if prestamo.modificado_por_id else '',
    ]


def exportar_prestamos_xlsx(queryset: Iterable[Prestamo]) -> bytes:
    """Genera Excel plano (sin rellenos de color) con todos los préstamos del queryset."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Préstamos'

    headers = [label for _, label in COLUMNAS]
    ws.append(headers)
    # Solo negrita en encabezado; sin colores de fondo ni fuente.
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True)

    for prestamo in queryset:
        ws.append(_fila_prestamo(prestamo))

    for col in ws.columns:
        max_len = 0
        letter = col[0].column_letter
        for cell in col:
            val = '' if cell.value is None else str(cell.value)
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[letter].width = min(max(12, max_len + 2), 40)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
