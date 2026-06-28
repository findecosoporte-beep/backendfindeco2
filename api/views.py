"""ViewSets de la API de prestamos."""

import calendar
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import ExtractMonth, ExtractWeekDay
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.graphics.barcode import qr
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .clientes_excel import (
    exportar_clientes_xlsx,
    generar_plantilla_clientes_xlsx,
    importar_clientes_xlsx,
)
from .estado_cuenta_export import exportar_estado_cuenta_pdf, recolectar_datos_estado_cuenta
from .historial_pagos_export import (
    exportar_historial_pagos_pdf,
    exportar_historial_pagos_xlsx,
    nombre_archivo_historial,
)
from .core.cuotas import extract_cuota_numero_from_documento
from .core.findeco_brand import dibujar_logo_ticket
from .core.money import round_money
from .core.prestamo_calc import (
    annual_rate_from_nominal,
    frecuencia_anual,
    periodic_rate_from_nominal,
    periods_from_months,
    plan_totales_desde_condiciones,
)
from .core.distribucion_pago import (
    abonado_por_cuota_desde_pagos,
    cuotas_pagadas_completas,
    pendiente_cuota,
)
from .core.reporte_saldos import monto_cuota_programada, saldos_reporte_integracion
from .cobrador_scope import (
    carteras_ids_para_usuario,
    filtrar_pagos_por_cobrador,
    filtrar_prestamos_por_cobrador,
    usuario_operativo_desde_request,
)
from .models import (
    Cartera,
    Cliente,
    ClienteDocumento,
    ContratoPrestamo,
    HistorialPrestamo,
    HojaCobroImpresion,
    Pago,
    Prestamo,
    PrestamoCuota,
    Servicio,
    Usuario,
    Zona,
)
from .permissions import RoleBasedAccessPermission
from .pagination import ClienteListPagination, ReporteIntegracionPagination
from .role_policy import WRITE_ADMIN, WRITE_COBROS, WRITE_CONTRATOS, WRITE_DOCUMENTOS
from .serializers import (
    CarteraSerializer,
    ClienteSerializer,
    ClienteDocumentoSerializer,
    ContratoPrestamoSerializer,
    HistorialPrestamoSerializer,
    PagoSerializer,
    PrestamoSerializer,
    PrestamoCuotaSerializer,
    ServicioSerializer,
    SimulacionPrestamoSerializer,
    UsuarioAsesorCreateSerializer,
    UsuarioAsesorUpdateSerializer,
    UsuarioCobradorCreateSerializer,
    UsuarioCobradorUpdateSerializer,
    UsuarioSerializer,
    ZonaSerializer,
)

AUTH_PERMISSION_CLASSES = (RoleBasedAccessPermission,)


def _build_pago_invoice_pdf(pago: Pago, ticket_format: str = '58') -> bytes:
    """Genera un PDF de factura con estilo ticket (58mm u 80mm)."""
    buffer = io.BytesIO()
    is_80mm = ticket_format == '80'
    ticket_w = (80 if is_80mm else 58) * mm
    ticket_h = 210 * mm
    pdf = canvas.Canvas(buffer, pagesize=(ticket_w, ticket_h))
    width, height = ticket_w, ticket_h

    cliente = pago.id_prestamo.id_cliente
    capital = round_money(Decimal(pago.capital))
    interes = round_money(Decimal(pago.interes))
    mora = round_money(Decimal(pago.mora))
    subtotal = round_money(capital + interes)
    total_pagado = round_money(subtotal + mora)

    x0 = 0
    y = height - 12 * mm

    def center_text(text: str, size: int = 9, bold: bool = False, step_mm: float = 4.6) -> None:
        nonlocal y
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.drawCentredString(x0 + (ticket_w / 2), y, text)
        y -= step_mm * mm

    def line() -> None:
        nonlocal y
        pdf.setStrokeColor(colors.HexColor('#111111'))
        pdf.setLineWidth(0.6)
        pdf.line(x0, y, x0 + ticket_w, y)
        y -= 3 * mm

    # Marco del ticket
    pdf.setStrokeColor(colors.HexColor('#111111'))
    pdf.setLineWidth(0.4)
    pdf.rect(x0 + 1 * mm, 6 * mm, ticket_w - 2 * mm, height - 12 * mm, stroke=1, fill=0)

    center_x = x0 + (ticket_w / 2)
    y = dibujar_logo_ticket(
        pdf,
        center_x,
        y,
        ticket_w - 4 * mm,
        14 if is_80mm else 11,
    )

    title_size = 10 if is_80mm else 9
    folio_size = 9 if is_80mm else 8
    center_text('FACTURA ELECTRONICA', title_size, True)
    center_text(f'F{pago.id_pago:03d}-{pago.id_prestamo.id_prestamo:08d}', folio_size, False, 4.8)
    line()

    body_size = 9 if is_80mm else 7.8
    pdf.setFont('Helvetica', body_size)
    pdf.drawString(x0 + 1 * mm, y, f'Senor(es): {cliente.nombre}')
    y -= 5 * mm
    pdf.drawString(x0 + 1 * mm, y, f'RUC/DNI: {cliente.dni}')
    y -= 5 * mm
    pdf.drawString(x0 + 1 * mm, y, f'Fecha: {pago.fecha_pago.isoformat()}')
    y -= 3 * mm
    line()

    # Encabezado de detalle tipo POS (columnas relativas al ancho del ticket).
    header_size = 8.5 if is_80mm else 7.6
    right_margin_x = x0 + ticket_w - 1 * mm
    importe_x = right_margin_x
    price_x = x0 + (ticket_w * 0.78)
    qty_x = x0 + (ticket_w * 0.62)
    producto_x = x0 + 1 * mm
    pdf.setFont('Helvetica-Bold', header_size)
    pdf.drawString(producto_x, y, 'Producto')
    pdf.drawRightString(qty_x, y, 'Cant.')
    pdf.drawRightString(price_x, y, 'Precio')
    pdf.drawRightString(importe_x, y, 'Importe')
    y -= 3 * mm
    line()

    detail_size = 8.5 if is_80mm else 7.6
    pdf.setFont('Helvetica', detail_size)
    unit_price = round_money(total_pagado)
    producto_label = f'CUOTA {pago.documento or "PAGO"}'
    if len(producto_label) > 18:
        producto_label = f'{producto_label[:18]}...'
    pdf.drawString(producto_x, y, producto_label)
    pdf.drawRightString(qty_x, y, '1.0')
    pdf.drawRightString(price_x, y, f'{unit_price:,.2f}')
    pdf.drawRightString(importe_x, y, f'{total_pagado:,.2f}')
    y -= 4.8 * mm
    line()

    # Totales.
    pdf.setFont('Helvetica', detail_size)
    totals = [
        ('OP. GRAVADAS', subtotal),
        ('MORA', mora),
        ('SUB TOTAL', subtotal),
    ]
    for label, amount in totals:
        pdf.drawString(producto_x, y, label)
        pdf.drawRightString(importe_x, y, f'L/ {amount:,.2f}')
        y -= 4.5 * mm

    pdf.setFont('Helvetica-Bold', 10 if is_80mm else 8.8)
    pdf.drawString(producto_x, y, 'TOTAL VENTA')
    pdf.drawRightString(importe_x, y, f'L/ {total_pagado:,.2f}')
    y -= 5.5 * mm
    line()

    # Datos extra y QR.
    meta_size = 8.5 if is_80mm else 7.6
    center_text(f'PRESTAMO: {pago.id_prestamo.numero_prestamo}', meta_size, True, 4.2)
    center_text(f'VENDEDOR(A): {pago.id_prestamo.asesor or "N/A"}', meta_size, True, 4.2)
    line()
    center_text('Representacion impresa de la factura electronica', 7.8 if is_80mm else 7, False, 3.8)
    center_text('Gracias por su preferencia', 8.5 if is_80mm else 7.6, False, 4.6)

    qr_payload = (
        f"PAGO:{pago.id_pago}|PRESTAMO:{pago.id_prestamo.numero_prestamo}|"
        f"CLIENTE:{cliente.dni}|FECHA:{pago.fecha_pago.isoformat()}|TOTAL:{total_pagado}"
    )
    qr_code = qr.QrCodeWidget(qr_payload)
    bounds = qr_code.getBounds()
    qr_size = (18 if is_80mm else 14) * mm
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    drawing = Drawing(qr_size, qr_size)
    drawing.add(qr_code)
    drawing.scale(qr_size / qr_width, qr_size / qr_height)
    qr_x = x0 + (ticket_w / 2) - (qr_size / 2)
    qr_y = max(17 * mm, y - qr_size)
    renderPDF.draw(drawing, pdf, qr_x, qr_y)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class HealthView(APIView):
    """Health check para App Platform / balanceadores."""

    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({'status': 'ok'})


class MeView(APIView):
    """Perfil del usuario JWT y vínculo con tabla operativa `usuarios`."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        """Retorna el perfil del usuario autenticado y su rol operativo vinculado."""
        user = request.user
        actor = usuario_operativo_desde_request(request)
        cartera_ids = carteras_ids_para_usuario(actor)
        carteras_payload: list[dict] = []
        if cartera_ids:
            carteras_payload = list(
                Cartera.objects.filter(id_cartera__in=cartera_ids).values(
                    'id_cartera', 'nombre', 'dia_cobro'
                )
            )
        return Response(
            {
                'username': user.get_username(),
                'email': user.email or '',
                'vinculado': actor is not None,
                'rol': actor.rol if actor else None,
                'nombre_operativo': actor.nombre if actor else None,
                'id_usuario': actor.id_usuario if actor else None,
                'carteras': carteras_payload,
            }
        )


MES_CORTO = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')
DIAS_SEMANA = ('Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb')
ESTADO_PRESTAMO_LABELS = {
    'activo': 'Activo',
    'pendiente_aprobacion': 'Pendiente',
    'pagado': 'Pagado',
    'mora': 'Mora',
    'cancelado': 'Cancelado',
}


def _ultimos_meses(n: int, referencia) -> list[tuple[int, int]]:
    """Devuelve pares (año, mes) desde los últimos n meses hasta referencia (inclusive)."""
    meses: list[tuple[int, int]] = []
    year = referencia.year
    month = referencia.month
    for _ in range(n):
        meses.append((year, month))
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    meses.reverse()
    return meses


class DashboardResumenView(APIView):
    """Métricas agregadas del sistema para el panel de control."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        hoy = timezone.now().date()
        anio = hoy.year

        totales = {
            'clientes': Cliente.objects.count(),
            'prestamos': Prestamo.objects.count(),
            'pagos': Pago.objects.count(),
            'historial': HistorialPrestamo.objects.count(),
            'usuarios': Usuario.objects.count(),
        }

        prestamos_mes = [0] * 12
        for row in (
            Prestamo.objects.filter(fecha_entrega__year=anio)
            .annotate(mes=ExtractMonth('fecha_entrega'))
            .values('mes')
            .annotate(total=Count('id_prestamo'))
        ):
            mes_idx = int(row['mes']) - 1
            if 0 <= mes_idx < 12:
                prestamos_mes[mes_idx] = row['total']

        pagos_mes = [0] * 12
        for row in (
            Pago.objects.filter(fecha_pago__year=anio)
            .annotate(mes=ExtractMonth('fecha_pago'))
            .values('mes')
            .annotate(total=Count('id_pago'))
        ):
            mes_idx = int(row['mes']) - 1
            if 0 <= mes_idx < 12:
                pagos_mes[mes_idx] = row['total']

        estados_raw = list(
            Prestamo.objects.values('estado').annotate(total=Count('id_prestamo')).order_by('estado'),
        )
        prestamos_por_estado = {
            'labels': [
                ESTADO_PRESTAMO_LABELS.get(row['estado'], row['estado'] or 'Sin estado')
                for row in estados_raw
            ],
            'valores': [row['total'] for row in estados_raw],
        }

        cobros_semana = [0] * 7
        for row in (
            Pago.objects.annotate(dia=ExtractWeekDay('fecha_pago'))
            .values('dia')
            .annotate(total=Count('id_pago'))
        ):
            dia_idx = int(row['dia']) - 1
            if 0 <= dia_idx < 7:
                cobros_semana[dia_idx] = row['total']

        meses_tendencia = _ultimos_meses(8, hoy)
        tendencia_labels = [f'{MES_CORTO[m - 1]} {str(y)[-2:]}' for y, m in meses_tendencia]
        monto_cobrado: list[float] = []
        monto_desembolsado: list[float] = []
        for year, month in meses_tendencia:
            cobro = Pago.objects.filter(fecha_pago__year=year, fecha_pago__month=month).aggregate(
                total=Sum(F('capital') + F('interes') + F('mora')),
            )['total']
            desembolso = Prestamo.objects.filter(fecha_entrega__year=year, fecha_entrega__month=month).aggregate(
                total=Sum('monto'),
            )['total']
            monto_cobrado.append(float(cobro or 0))
            monto_desembolsado.append(float(desembolso or 0))

        ultimos_prestamos = []
        prestamos_qs = Prestamo.objects.select_related('id_cliente').order_by('-fecha_entrega', '-id_prestamo')[:25]
        prestamo_ids = [p.id_prestamo for p in prestamos_qs]
        ultimo_pago_por_prestamo: dict[int, Pago] = {}
        if prestamo_ids:
            for pago in Pago.objects.filter(id_prestamo_id__in=prestamo_ids).order_by(
                'id_prestamo_id',
                '-fecha_pago',
                '-id_pago',
            ):
                if pago.id_prestamo_id not in ultimo_pago_por_prestamo:
                    ultimo_pago_por_prestamo[pago.id_prestamo_id] = pago

        for prestamo in prestamos_qs:
            ultimo_pago = ultimo_pago_por_prestamo.get(prestamo.id_prestamo)
            ultimos_prestamos.append(
                {
                    'id_prestamo': prestamo.id_prestamo,
                    'numero_prestamo': prestamo.numero_prestamo,
                    'id_cliente': prestamo.id_cliente_id,
                    'cliente_nombre': prestamo.id_cliente.nombre if prestamo.id_cliente else '',
                    'producto': prestamo.producto,
                    'estado': prestamo.estado,
                    'monto': str(prestamo.monto),
                    'interes': str(ultimo_pago.interes if ultimo_pago else 0),
                    'saldo': str(ultimo_pago.saldo if ultimo_pago else prestamo.monto),
                    'fecha_entrega': prestamo.fecha_entrega.isoformat() if prestamo.fecha_entrega else None,
                },
            )

        historial_filas = []
        if totales['historial'] > 0:
            for item in HistorialPrestamo.objects.select_related('id_cliente').order_by('-id_historial')[:25]:
                historial_filas.append(
                    {
                        'id_historial': item.id_historial,
                        'numero_prestamo': item.numero_prestamo,
                        'id_cliente': item.id_cliente_id,
                        'cliente_nombre': item.id_cliente.nombre if item.id_cliente else '',
                        'producto': item.producto,
                        'monto': str(item.monto),
                        'interes': str(item.interes),
                        'saldo': str(item.saldo) if item.saldo is not None else None,
                    },
                )

        return Response(
            {
                'totales': totales,
                'registros_mensuales': {
                    'labels': list(MES_CORTO),
                    'prestamos': prestamos_mes,
                    'pagos': pagos_mes,
                },
                'prestamos_por_estado': prestamos_por_estado,
                'actividad_semanal': {
                    'labels': list(DIAS_SEMANA),
                    'cobros': cobros_semana,
                },
                'tendencia_mensual': {
                    'labels': tendencia_labels,
                    'monto_cobrado': monto_cobrado,
                    'monto_desembolsado': monto_desembolsado,
                },
                'ultimos_prestamos': ultimos_prestamos,
                'historial_prestamos': historial_filas,
            },
        )


class SimulacionPrestamoView(APIView):
    """Calcula cuota e interes con esquema de interes simple por periodo."""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        """Simula el prestamo con interes simple y devuelve tabla de amortizacion."""
        serializer = SimulacionPrestamoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        monto = Decimal(data['monto'])
        plazo_meses = int(data['plazo'])
        forma_pago = data['forma_pago']
        tasa_nominal_pct = Decimal(data['tasa_interes'])
        tasa_anual_pct = annual_rate_from_nominal(tasa_nominal_pct)
        tasa_periodica = periodic_rate_from_nominal(tasa_nominal_pct, forma_pago) / Decimal('100')
        comision_pct = Decimal(data['comision']) / Decimal('100')

        frecuencia = frecuencia_anual(forma_pago)
        periodos = periods_from_months(plazo_meses, forma_pago)
        capital_fijo = round_money(monto / Decimal(periodos))
        interes_fijo = round_money(monto * tasa_periodica)
        cuota = round_money(capital_fijo + interes_fijo)
        saldo = monto
        amortizacion = []
        total_interes = Decimal('0.00')

        for periodo in range(1, periodos + 1):
            interes = interes_fijo
            capital = capital_fijo
            cuota_final = cuota

            if periodo == periodos:
                capital = saldo
                cuota_final = round_money(capital + interes)

            saldo = round_money(saldo - capital)
            if saldo < 0:
                saldo = Decimal('0.00')
            total_interes += interes

            amortizacion.append(
                {
                    'periodo': periodo,
                    'cuota': float(cuota_final),
                    'capital': float(round_money(capital)),
                    'interes': float(interes),
                    'saldo': float(saldo),
                }
            )

        total_interes = round_money(total_interes)
        comision_monto = round_money(monto * comision_pct)
        total_pagar = round_money(monto + total_interes + comision_monto)

        return Response(
            {
                'monto': float(round_money(monto)),
                'plazo': periodos,
                'forma_pago': forma_pago,
                'tasa_interes': float(data['tasa_interes']),
                'tasa_anual': float(round_money(tasa_anual_pct)),
                'comision': float(data['comision']),
                'frecuencia_anual': frecuencia,
                'cuota_periodica': float(cuota),
                'total_interes': float(total_interes),
                'comision_monto': float(comision_monto),
                'total_pagar': float(total_pagar),
                'amortizacion': amortizacion,
            }
        )


class ClienteViewSet(viewsets.ModelViewSet):
    """CRUD de clientes del sistema."""

    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    pagination_class = ClienteListPagination
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    search_fields = ['dni', 'telefono', 'nombre']
    filterset_fields = ['id_cliente', 'dni']
    ordering_fields = ['id_cliente', 'nombre']

    def get_queryset(self):
        qs = Cliente.objects.all()
        if self.action == 'list':
            qs = qs.annotate(prestamos_count=Count('prestamo'))
        return qs

    @action(detail=False, methods=['get'], url_path='exportar-excel')
    def exportar_excel(self, request):
        """Descarga todos los clientes en formato Excel."""
        content = exportar_clientes_xlsx(self.filter_queryset(Cliente.objects.all()))
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="clientes_findeco.xlsx"'
        return response

    @action(detail=False, methods=['get'], url_path='plantilla-excel')
    def plantilla_excel(self, request):
        """Descarga plantilla Excel para carga masiva de clientes."""
        content = generar_plantilla_clientes_xlsx()
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_clientes_findeco.xlsx"'
        return response

    @action(
        detail=False,
        methods=['post'],
        url_path='importar-excel',
        parser_classes=[MultiPartParser, FormParser],
    )
    def importar_excel(self, request):
        """Importa clientes desde un archivo Excel (.xlsx)."""
        archivo = request.FILES.get('archivo')
        if archivo is None:
            return Response(
                {'detail': 'Debe enviar el archivo en el campo «archivo».'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not str(archivo.name or '').lower().endswith('.xlsx'):
            return Response(
                {'detail': 'Solo se admiten archivos .xlsx.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        actualizar = str(request.data.get('actualizar_existentes', '')).lower() in (
            '1',
            'true',
            'yes',
            'si',
            'sí',
        )
        try:
            resultado = importar_clientes_xlsx(archivo, actualizar_existentes=actualizar)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)

    @action(detail=True, methods=['post'], url_path='finalizar-expediente')
    def finalizar_expediente(self, request, pk=None) -> Response:
        """Aprueba préstamo pendiente si aplica y guarda actividad económica / observaciones del cliente."""
        cliente: Cliente = self.get_object()
        actividad_in = (
            (request.data.get('actividad_economica') or request.data.get('ocupacion') or request.data.get('notas') or '')
            .strip()
        )
        actor = (request.data.get('actor') or '').strip()
        if not actor and request.user and getattr(request.user, 'is_authenticated', False):
            try:
                actor = request.user.get_username()
            except (AttributeError, TypeError):
                actor = str(request.user)
        if actividad_in and actor:
            texto = f'{actividad_in} — (Operador: {actor})'
        elif actividad_in:
            texto = actividad_in
        elif actor:
            texto = f'Documentación cerrada (operador: {actor}).'
        else:
            texto = ''
        id_prestamo = request.data.get('id_prestamo')
        prestamo_to_approve = None
        if id_prestamo is not None and str(id_prestamo).strip() != '':
            prestamo_to_approve = Prestamo.objects.filter(
                id_prestamo=id_prestamo,
                id_cliente=cliente,
            ).first()
        if prestamo_to_approve is None:
            prestamo_to_approve = Prestamo.objects.filter(
                id_cliente=cliente,
                estado='pendiente_aprobacion',
            ).order_by('-id_prestamo').first()
        if prestamo_to_approve is not None:
            prestamo_to_approve.estado = 'activo'
            prestamo_to_approve.save(update_fields=['estado'])

        update_fields: list[str] = []
        if texto:
            cliente.actividad_economica = texto
            update_fields.append('actividad_economica')
        if update_fields:
            cliente.save(update_fields=update_fields)
        return Response(ClienteSerializer(cliente).data)


class ClienteDocumentoViewSet(viewsets.ModelViewSet):
    """Gestión de documentos cargados y actividad por cliente."""

    queryset = ClienteDocumento.objects.select_related('id_cliente').all()
    serializer_class = ClienteDocumentoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_DOCUMENTOS
    filterset_fields = ['id_cliente']
    ordering_fields = ['creado_en', 'id_documento']


class ContratoPrestamoViewSet(viewsets.ModelViewSet):
    """Gestión de contratos de préstamo editables por cliente."""

    queryset = ContratoPrestamo.objects.select_related('id_cliente', 'id_prestamo', 'id_documento').all()
    serializer_class = ContratoPrestamoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_CONTRATOS
    filterset_fields = ['id_cliente', 'id_prestamo', 'id_documento', 'actor']
    ordering_fields = ['creado_en', 'actualizado_en', 'id_contrato']


class UsuarioViewSet(viewsets.ModelViewSet):
    """Consulta, alta, edición y baja de perfiles operativos (asesores y cobradores)."""

    queryset = Usuario.objects.all()
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    http_method_names = ['get', 'head', 'options', 'post', 'patch', 'delete']
    serializer_class = UsuarioSerializer
    search_fields = ['nombre', 'correo', 'rol']
    filterset_fields = ['rol']
    ordering_fields = ['id_usuario', 'nombre']

    def get_serializer_class(self):
        if self.action == 'create':
            if str(self.request.data.get('rol', '')).strip() == 'cobrador':
                return UsuarioCobradorCreateSerializer
            return UsuarioAsesorCreateSerializer
        if self.action in ('update', 'partial_update'):
            instance = self.get_object()
            if instance.rol == 'cobrador':
                return UsuarioCobradorUpdateSerializer
            return UsuarioAsesorUpdateSerializer
        return UsuarioSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        return Response(UsuarioSerializer(usuario).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if instance.rol not in ('asesor', 'cobrador'):
            return Response(
                {'detail': 'Solo se pueden editar perfiles con rol asesor o cobrador.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        return Response(UsuarioSerializer(usuario).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.rol not in ('asesor', 'cobrador'):
            return Response(
                {'detail': 'Solo se pueden eliminar perfiles con rol asesor o cobrador.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        correo = instance.correo
        UserModel = get_user_model()
        try:
            with transaction.atomic():
                instance.delete()
                auth_user = UserModel.objects.filter(email__iexact=correo).first()
                if auth_user:
                    auth_user.delete()
        except IntegrityError as exc:
            raise ValidationError(
                'No se puede eliminar el usuario porque tiene préstamos u otros registros vinculados.',
            ) from exc


class ZonaViewSet(viewsets.ModelViewSet):
    """Catálogo de zonas territoriales (lectura y alta con día de semana)."""

    queryset = Zona.objects.all()
    serializer_class = ZonaSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    search_fields = ['nombre', 'codigo']
    ordering_fields = ['id_zona', 'nombre', 'codigo', 'dia_semana']


class CarteraViewSet(viewsets.ModelViewSet):
    """CRUD de carteras operativas (nombre y día de cobro)."""

    queryset = Cartera.objects.all()
    serializer_class = CarteraSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    search_fields = ['nombre', 'dia_cobro']
    ordering_fields = ['id_cartera', 'nombre', 'dia_cobro']


def _cargar_auxiliar_reporte_integracion(ids: list[int]) -> tuple[
    dict[int, Decimal],
    dict[int, list[PrestamoCuota]],
    dict[int, set[int]],
    dict[int, Pago],
    dict[int, Decimal],
    dict[int, dict[int, Decimal]],
]:
    """Cuotas, pagos y abonos por préstamo para el reporte de integración."""
    primera_cuota: dict[int, Decimal] = {}
    cuotas_por_prestamo: dict[int, list[PrestamoCuota]] = defaultdict(list)
    if ids:
        for c in (
            PrestamoCuota.objects.filter(id_prestamo_id__in=ids)
            .order_by('id_prestamo_id', 'numero_cuota')
            .only(
                'id_prestamo_id',
                'total_programado',
                'servicios_programado',
                'otros_programado',
                'numero_cuota',
                'fecha_programada',
                'capital_programado',
                'interes_programado',
                'saldo_capital_programado',
            )
        ):
            if c.id_prestamo_id not in primera_cuota:
                primera_cuota[c.id_prestamo_id] = c.total_programado
            cuotas_por_prestamo[c.id_prestamo_id].append(c)

    pagos_por_prestamo: dict[int, list[Pago]] = defaultdict(list)
    abonado_por_prestamo: dict[int, Decimal] = defaultdict(lambda: Decimal('0.00'))
    if ids:
        for pg in (
            Pago.objects.filter(id_prestamo_id__in=ids)
            .only('id_prestamo_id', 'documento', 'capital', 'interes', 'mora')
            .iterator()
        ):
            pagos_por_prestamo[pg.id_prestamo_id].append(pg)
            abonado_por_prestamo[pg.id_prestamo_id] += (
                Decimal(pg.capital) + Decimal(pg.interes) + Decimal(pg.mora)
            )

    abonado_cuota_por_prestamo: dict[int, dict[int, Decimal]] = {}
    cuotas_pagadas_nums: dict[int, set[int]] = {}
    for pid in ids:
        abonado_cuota = abonado_por_cuota_desde_pagos(pagos_por_prestamo.get(pid, []))
        abonado_cuota_por_prestamo[pid] = abonado_cuota
        plan = cuotas_por_prestamo.get(pid, [])
        cuotas_pagadas_nums[pid] = cuotas_pagadas_completas(plan, abonado_cuota) if plan else set()

    ultimo_pago_por: dict[int, Pago] = {}
    if ids:
        for pay in (
            Pago.objects.filter(id_prestamo_id__in=ids)
            .order_by('id_prestamo_id', '-fecha_pago', '-id_pago')
            .only('id_prestamo_id', 'saldo', 'fecha_pago', 'id_pago')
        ):
            if pay.id_prestamo_id not in ultimo_pago_por:
                ultimo_pago_por[pay.id_prestamo_id] = pay

    return (
        primera_cuota,
        cuotas_por_prestamo,
        cuotas_pagadas_nums,
        ultimo_pago_por,
        abonado_por_prestamo,
        abonado_cuota_por_prestamo,
    )


def _montos_reporte_integracion(
    p: Prestamo,
    primera_cuota: dict[int, Decimal],
    plan_rows: list[PrestamoCuota],
    paid_nums: set[int],
    abonado_total: Decimal,
    abonado_por_cuota: dict[int, Decimal] | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Retorna saldo inicial (cap+int), cuota planificada y saldo pendiente (cap+int)."""
    saldo_inicial, saldo_actual = saldos_reporte_integracion(
        p,
        plan_rows,
        abonado_por_cuota,
        abonado_total,
        paid_nums=paid_nums,
    )
    if p.id_prestamo in primera_cuota:
        cuota_pl = round_money(Decimal(primera_cuota[p.id_prestamo]))
    elif plan_rows:
        cuota_pl = round_money(Decimal(plan_rows[0].total_programado))
    else:
        _, cuota_pl = plan_totales_desde_condiciones(
            Decimal(p.monto),
            int(p.plazo),
            p.forma_pago,
            Decimal(p.tasa_interes),
        )
    return saldo_inicial, cuota_pl, saldo_actual


def _fila_reporte_integracion(
    p: Prestamo,
    primera_cuota: dict[int, Decimal],
    cuotas_por_prestamo: dict[int, list[PrestamoCuota]],
    cuotas_pagadas_nums: dict[int, set[int]],
    abonado_por_prestamo: dict[int, Decimal],
    abonado_cuota_por_prestamo: dict[int, dict[int, Decimal]],
) -> dict:
    plan_rows = cuotas_por_prestamo.get(p.id_prestamo, [])
    paid_nums = cuotas_pagadas_nums.get(p.id_prestamo, set())
    abonado_cuota = abonado_cuota_por_prestamo.get(p.id_prestamo, {})
    saldo_inicial, cuota_pl, saldo_act = _montos_reporte_integracion(
        p,
        primera_cuota,
        plan_rows,
        paid_nums,
        abonado_por_prestamo.get(p.id_prestamo, Decimal('0.00')),
        abonado_por_cuota=abonado_cuota if plan_rows else None,
    )

    asesor_txt = (p.asesor or '').strip()
    if not asesor_txt and p.id_usuario_id:
        asesor_txt = (getattr(p.id_usuario, 'nombre', None) or '').strip()

    siguiente = next(
        (
            row
            for row in plan_rows
            if pendiente_cuota(row, abonado_cuota.get(row.numero_cuota, Decimal('0.00'))) > 0
        ),
        None,
    )

    hoy = timezone.localdate()
    cuotas_atrasadas_nums = [
        row.numero_cuota
        for row in plan_rows
        if pendiente_cuota(row, abonado_cuota.get(row.numero_cuota, Decimal('0.00'))) > 0
        and row.fecha_programada < hoy
    ]

    sig_fields: dict = {
        'cuota_siguiente_numero': None,
        'cuota_siguiente_fecha': None,
        'cuota_siguiente_monto': None,
        'cuota_siguiente_capital': None,
        'cuota_siguiente_interes': None,
        'cuota_siguiente_saldo_capital': None,
        'cuotas_atrasadas': len(cuotas_atrasadas_nums),
        'cuotas_atrasadas_numeros': (
            ', '.join(str(n) for n in cuotas_atrasadas_nums) if cuotas_atrasadas_nums else ''
        ),
    }
    if siguiente is not None:
        pendiente_sig = pendiente_cuota(
            siguiente,
            abonado_cuota.get(siguiente.numero_cuota, Decimal('0.00')),
        )
        sig_fields.update(
            {
                'cuota_siguiente_numero': siguiente.numero_cuota,
                'cuota_siguiente_fecha': siguiente.fecha_programada.isoformat(),
                'cuota_siguiente_monto': str(round_money(pendiente_sig)),
                'cuota_siguiente_capital': str(round_money(Decimal(siguiente.capital_programado))),
                'cuota_siguiente_interes': str(round_money(Decimal(siguiente.interes_programado))),
                'cuota_siguiente_saldo_capital': str(
                    round_money(Decimal(siguiente.saldo_capital_programado))
                ),
            }
        )

    cartera = p.id_cartera
    cliente = p.id_cliente

    row_data = {
        'id_prestamo': p.id_prestamo,
        'numero_prestamo': p.numero_prestamo,
        'nombre_cliente': cliente.nombre,
        'telefono': (getattr(cliente, 'telefono', None) or '').strip(),
        'id_cartera': p.id_cartera_id,
        'cartera_nombre': (cartera.nombre if cartera else '').strip(),
        'cartera_dia_cobro': (cartera.dia_cobro if cartera else '') or '',
        'cliente_dia_cobro_semanal': (getattr(cliente, 'dia_cobro_semanal', None) or '') or '',
        'fecha_entrega': p.fecha_entrega.isoformat(),
        'fecha_vencimiento': p.fecha_vencimiento.isoformat(),
        'dias_mora': int(p.dias_mora or 0),
        'saldo_inicial': str(saldo_inicial),
        'cuota': str(cuota_pl),
        'saldo_actual': str(saldo_act),
        'ciclos': int(p.ciclos or 0),
        'asesor': asesor_txt,
        'estado': p.estado,
        'forma_pago': p.forma_pago,
        'sucursal': (p.sucursal or '').strip() or (p.id_zona.nombre if p.id_zona_id else ''),
        'plazo': int(p.plazo or 0),
    }
    row_data.update(sig_fields)
    return row_data


class PrestamoViewSet(viewsets.ModelViewSet):
    """CRUD de prestamos con filtros de negocio."""

    queryset = Prestamo.objects.select_related('id_cliente', 'id_usuario', 'id_zona', 'id_cartera').all()
    serializer_class = PrestamoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    search_fields = ['numero_prestamo', 'id_cliente__nombre', 'producto', 'estado']
    filterset_fields = [
        'estado',
        'forma_pago',
        'id_cliente',
        'id_usuario',
        'numero_prestamo',
        'id_zona',
        'id_cartera',
        'fecha_entrega',
        'fecha_vencimiento',
    ]
    ordering_fields = ['id_prestamo', 'monto', 'fecha_vencimiento', 'dias_mora']

    def get_queryset(self):
        qs = Prestamo.objects.select_related('id_cliente', 'id_usuario', 'id_zona', 'id_cartera').all()
        return filtrar_prestamos_por_cobrador(qs, self.request)

    @action(detail=False, methods=['get'], url_path='reporte-integracion')
    def reporte_integracion(self, request):
        """Listado agregado tipo reporte de cartera: cuota planificada y saldo desde último pago."""
        # Sin filter_queryset: django-filter espera estado=valor_único; aquí pasamos estado=a,b,c
        # y produciría 400. Solo usamos queryset base del viewset + filtros manuales siguientes.
        qs = self.get_queryset()

        estado_param = (request.query_params.get('estado') or '').strip()
        if estado_param:
            lista = [e.strip() for e in estado_param.split(',') if e.strip()]
            if lista:
                qs = qs.filter(estado__in=lista)

        zona_param = (request.query_params.get('id_zona') or '').strip()
        if zona_param.isdigit():
            qs = qs.filter(id_zona_id=int(zona_param))

        cartera_param = (request.query_params.get('id_cartera') or '').strip()
        if cartera_param.isdigit():
            qs = qs.filter(id_cartera_id=int(cartera_param))

        id_cliente_param = (request.query_params.get('id_cliente') or '').strip()
        if id_cliente_param.isdigit():
            qs = qs.filter(id_cliente_id=int(id_cliente_param))

        id_prestamo_param = (request.query_params.get('id_prestamo') or '').strip()
        if id_prestamo_param.isdigit():
            qs = qs.filter(id_prestamo=int(id_prestamo_param))

        fd = (request.query_params.get('fecha_entrega_desde') or '').strip()
        if fd:
            qs = qs.filter(fecha_entrega__gte=fd)
        fh = (request.query_params.get('fecha_entrega_hasta') or '').strip()
        if fh:
            qs = qs.filter(fecha_entrega__lte=fh)

        forma_pago_param = (request.query_params.get('forma_pago') or '').strip()
        if forma_pago_param:
            valid_forma = {'semanal', 'mensual', 'quincenal'}
            if forma_pago_param in valid_forma:
                qs = qs.filter(forma_pago=forma_pago_param)

        prestamos_qs = qs.order_by('numero_prestamo')
        ids = list(prestamos_qs.values_list('id_prestamo', flat=True))
        fecha_reporte = timezone.localdate().isoformat()

        if not ids:
            resumen_vacio = {
                'clientes_distintos': 0,
                'prestamos': 0,
                'total_cuotas_plazo': 0,
                'total_saldo_inicial': '0',
                'total_saldo_actual': '0',
                'total_cuota': '0',
            }
            return Response(
                {
                    'fecha_reporte': fecha_reporte,
                    'count': 0,
                    'page': 1,
                    'next': None,
                    'previous': None,
                    'filas': [],
                    'resumen': resumen_vacio,
                }
            )

        (
            primera_cuota,
            cuotas_por_prestamo,
            cuotas_pagadas_nums,
            _ultimo_pago_por,
            abonado_por_prestamo,
            abonado_cuota_por_prestamo,
        ) = _cargar_auxiliar_reporte_integracion(ids)

        clientes_ids: set[int] = set()
        sum_inicial = Decimal('0')
        sum_cuota = Decimal('0')
        sum_actual = Decimal('0')
        sum_plazo = 0
        for p in prestamos_qs:
            clientes_ids.add(p.id_cliente_id)
            plan_rows = cuotas_por_prestamo.get(p.id_prestamo, [])
            paid_nums = cuotas_pagadas_nums.get(p.id_prestamo, set())
            abonado_cuota = abonado_cuota_por_prestamo.get(p.id_prestamo, {})
            saldo_inicial, cuota_pl, saldo_act = _montos_reporte_integracion(
                p,
                primera_cuota,
                plan_rows,
                paid_nums,
                abonado_por_prestamo.get(p.id_prestamo, Decimal('0.00')),
                abonado_por_cuota=abonado_cuota if plan_rows else None,
            )
            sum_inicial += saldo_inicial
            sum_cuota += cuota_pl
            sum_actual += saldo_act
            sum_plazo += int(p.plazo or 0)

        resumen = {
            'clientes_distintos': len(clientes_ids),
            'prestamos': len(ids),
            'total_cuotas_plazo': sum_plazo,
            'total_saldo_inicial': str(round_money(sum_inicial)),
            'total_saldo_actual': str(round_money(sum_actual)),
            'total_cuota': str(round_money(sum_cuota)),
        }

        all_rows = (request.query_params.get('all') or '').strip().lower() in ('1', 'true', 'yes')

        def _build_filas(prestamos_page: list[Prestamo]) -> list[dict]:
            return [
                _fila_reporte_integracion(
                    p,
                    primera_cuota,
                    cuotas_por_prestamo,
                    cuotas_pagadas_nums,
                    abonado_por_prestamo,
                    abonado_cuota_por_prestamo,
                )
                for p in prestamos_page
            ]

        if all_rows:
            return Response(
                {
                    'fecha_reporte': fecha_reporte,
                    'filas': _build_filas(list(prestamos_qs)),
                    'resumen': resumen,
                }
            )

        pagination = ReporteIntegracionPagination()
        page_size = pagination.get_page_size(request) or pagination.page_size
        paginator = Paginator(prestamos_qs, page_size)
        page_number = request.query_params.get(pagination.page_query_param, 1)
        page_obj = paginator.get_page(page_number)

        payload = {
            'fecha_reporte': fecha_reporte,
            'count': paginator.count,
            'page': page_obj.number,
            'next': None,
            'previous': None,
            'filas': _build_filas(list(page_obj.object_list)),
            'resumen': resumen,
        }
        if page_obj.has_next():
            q = request.query_params.copy()
            q[pagination.page_query_param] = str(page_obj.next_page_number())
            payload['next'] = request.build_absolute_uri(f'{request.path}?{q.urlencode()}')
        if page_obj.has_previous():
            q = request.query_params.copy()
            q[pagination.page_query_param] = str(page_obj.previous_page_number())
            payload['previous'] = request.build_absolute_uri(f'{request.path}?{q.urlencode()}')

        return Response(payload)

    @action(detail=False, methods=['post'], url_path='registrar-impresion-hoja-cobros')
    def registrar_impresion_hoja_cobros(self, request):
        """Registra una impresión de hoja de cobros y devuelve correlativo persistente."""
        total_raw = request.data.get('total_registros', 0)
        try:
            total_registros = int(total_raw)
        except (TypeError, ValueError):
            return Response({'detail': 'total_registros debe ser un número entero.'}, status=400)
        if total_registros < 0:
            return Response({'detail': 'total_registros no puede ser negativo.'}, status=400)

        actor = Usuario.objects.filter(correo=request.user.email).only('id_usuario').first()
        with transaction.atomic():
            ultima = (
                HojaCobroImpresion.objects.select_for_update()
                .order_by('-numero_impresion')
                .only('numero_impresion')
                .first()
            )
            siguiente = (ultima.numero_impresion if ultima else 0) + 1
            row = HojaCobroImpresion.objects.create(
                numero_impresion=siguiente,
                generado_por=actor,
                total_registros=total_registros,
            )

        return Response(
            {
                'id_impresion': row.id_impresion,
                'numero_impresion': row.numero_impresion,
                'creado_en': row.creado_en.isoformat(),
                'total_registros': row.total_registros,
                'id_usuario': row.generado_por_id,
            },
            status=201,
        )

    @action(detail=True, methods=['get'], url_path='estado-cuenta-pdf')
    def estado_cuenta_pdf(self, request, pk=None):
        """Retorna un PDF con el estado de cuenta del préstamo."""
        prestamo = self.get_object()
        datos = recolectar_datos_estado_cuenta(prestamo)
        pdf_content = exportar_estado_cuenta_pdf(datos)
        slug = (prestamo.numero_prestamo or str(prestamo.id_prestamo)).replace(' ', '-')
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="estado-cuenta-{slug}.pdf"'
        return response


def _rango_periodo_historial_pagos(
    modo: str,
    fecha_str: str | None,
    mes_str: str | None,
    anio_str: str | None,
) -> tuple[date, date]:
    """Devuelve (inicio, fin) inclusive para modo día, mes o año."""
    hoy = timezone.localdate()
    modo_norm = (modo or 'dia').strip().lower()
    try:
        anio = int(anio_str) if anio_str else hoy.year
    except (TypeError, ValueError) as exc:
        raise ValidationError({'anio': 'Año inválido.'}) from exc

    if modo_norm == 'dia':
        parsed = parse_date((fecha_str or '').strip())
        if parsed is None:
            raise ValidationError({'fecha': 'Indique una fecha válida (AAAA-MM-DD).'})
        return parsed, parsed

    if modo_norm == 'mes':
        try:
            mes = int(mes_str) if mes_str else hoy.month
        except (TypeError, ValueError) as exc:
            raise ValidationError({'mes': 'Mes inválido (1-12).'}) from exc
        if mes < 1 or mes > 12:
            raise ValidationError({'mes': 'Mes inválido (1-12).'})
        ultimo = calendar.monthrange(anio, mes)[1]
        return date(anio, mes, 1), date(anio, mes, ultimo)

    if modo_norm == 'anio':
        return date(anio, 1, 1), date(anio, 12, 31)

    raise ValidationError({'modo': 'Use modo=dia, modo=mes o modo=anio.'})


def _datos_historial_pagos_cobros(request) -> dict:
    """Arma el historial de pagos por día, mes o año."""
    modo = request.query_params.get('modo', 'dia')
    fecha_str = request.query_params.get('fecha')
    mes_str = request.query_params.get('mes')
    anio_str = request.query_params.get('anio')
    id_cartera_raw = request.query_params.get('id_cartera')

    inicio, fin = _rango_periodo_historial_pagos(modo, fecha_str, mes_str, anio_str)

    qs = (
        Pago.objects.filter(fecha_pago__gte=inicio, fecha_pago__lte=fin)
        .select_related(
            'id_prestamo',
            'id_prestamo__id_cliente',
            'id_prestamo__id_cartera',
        )
        .order_by('fecha_pago', 'id_pago')
    )
    qs = filtrar_pagos_por_cobrador(qs, request)

    cartera_etiqueta = 'Todas las carteras'
    if id_cartera_raw:
        try:
            id_cartera = int(id_cartera_raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError({'id_cartera': 'Cartera inválida.'}) from exc
        actor = usuario_operativo_desde_request(request)
        if actor is not None and actor.rol == 'cobrador':
            permitidas = carteras_ids_para_usuario(actor)
            if id_cartera not in permitidas:
                raise ValidationError({'id_cartera': 'Cartera no asignada a su usuario.'})
        qs = qs.filter(id_prestamo__id_cartera_id=id_cartera)
        cartera = Cartera.objects.filter(pk=id_cartera).only('nombre').first()
        if cartera:
            cartera_etiqueta = cartera.nombre

    filas = []
    tot_capital = Decimal('0.00')
    tot_interes = Decimal('0.00')
    tot_mora = Decimal('0.00')

    for pg in qs:
        prestamo = pg.id_prestamo
        cliente = prestamo.id_cliente if prestamo else None
        cartera = prestamo.id_cartera if prestamo else None
        capital = Decimal(pg.capital)
        interes = Decimal(pg.interes)
        mora = Decimal(pg.mora)
        tot_capital += capital
        tot_interes += interes
        tot_mora += mora
        filas.append(
            {
                'id_pago': pg.id_pago,
                'fecha_pago': pg.fecha_pago.isoformat(),
                'documento': pg.documento,
                'capital': str(round_money(capital)),
                'interes': str(round_money(interes)),
                'mora': str(round_money(mora)),
                'total': str(round_money(capital + interes + mora)),
                'id_prestamo': prestamo.id_prestamo if prestamo else None,
                'numero_prestamo': prestamo.numero_prestamo if prestamo else '',
                'nombre_cliente': cliente.nombre if cliente else '',
                'dni_cliente': cliente.dni if cliente else '',
                'cartera_nombre': cartera.nombre if cartera else '',
            }
        )

    total_cobrado = round_money(tot_capital + tot_interes + tot_mora)
    return {
        'modo': (modo or 'dia').strip().lower(),
        'fecha_inicio': inicio.isoformat(),
        'fecha_fin': fin.isoformat(),
        'cartera_etiqueta': cartera_etiqueta,
        'filas': filas,
        'resumen': {
            'registros': len(filas),
            'total_capital': str(round_money(tot_capital)),
            'total_interes': str(round_money(tot_interes)),
            'total_mora': str(round_money(tot_mora)),
            'total_cobrado': str(total_cobrado),
        },
    }


def _respuesta_historial_pagos_cobros(request) -> Response:
    return Response(_datos_historial_pagos_cobros(request))


class PagoViewSet(viewsets.ModelViewSet):
    """CRUD de pagos asociados a prestamos."""

    queryset = Pago.objects.select_related('id_prestamo').all()
    serializer_class = PagoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_COBROS
    search_fields = ['documento']
    filterset_fields = {
        'id_prestamo': ['exact'],
        'fecha_pago': ['exact', 'gte', 'lte'],
    }
    ordering_fields = ['id_pago', 'fecha_pago']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pago = serializer.save()
        data = serializer.data
        if serializer.distribucion_resumen:
            data = {**data, 'distribucion': serializer.distribucion_resumen}
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'], url_path='historial-cobros')
    def historial_cobros(self, request):
        """Historial de pagos cobrados filtrado por día, mes o año (para impresión)."""
        return _respuesta_historial_pagos_cobros(request)

    @action(detail=False, methods=['get'], url_path='historial-cobros-excel')
    def historial_cobros_excel(self, request):
        """Exporta el historial de pagos a Excel (.xlsx)."""
        datos = _datos_historial_pagos_cobros(request)
        content = exportar_historial_pagos_xlsx(datos)
        filename = nombre_archivo_historial(datos, 'xlsx')
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=['get'], url_path='historial-cobros-pdf')
    def historial_cobros_pdf(self, request):
        """Exporta el historial de pagos a PDF."""
        datos = _datos_historial_pagos_cobros(request)
        content = exportar_historial_pagos_pdf(datos)
        filename = nombre_archivo_historial(datos, 'pdf')
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=['get'], url_path='factura-pdf')
    def factura_pdf(self, request, pk=None):
        """Retorna un PDF imprimible de factura para un pago."""
        pago = self.get_object()
        ticket_format = request.query_params.get('ticket', '58').strip()
        if ticket_format not in ('58', '80'):
            ticket_format = '58'
        pdf_content = _build_pago_invoice_pdf(pago, ticket_format=ticket_format)
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'inline; filename="factura-pago-{pago.id_pago}-{ticket_format}mm.pdf"'
        )
        return response


class PrestamoCuotaViewSet(viewsets.ModelViewSet):
    """CRUD del plan de pagos por cuota de cada prestamo."""

    queryset = PrestamoCuota.objects.select_related('id_prestamo').all()
    serializer_class = PrestamoCuotaSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    filterset_fields = ['id_prestamo', 'numero_cuota', 'estado', 'fecha_programada']
    ordering_fields = ['id_cuota', 'numero_cuota', 'fecha_programada']


class ServicioViewSet(viewsets.ModelViewSet):
    """CRUD de servicios financieros por prestamo."""

    queryset = Servicio.objects.select_related('id_prestamo').all()
    serializer_class = ServicioSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = WRITE_ADMIN
    search_fields = ['nombre_servicio']
    filterset_fields = ['id_prestamo', 'codigo_servicio']
    ordering_fields = ['id_servicio', 'codigo_servicio']


class HistorialPrestamoViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de historial de prestamos (solo lectura)."""

    queryset = HistorialPrestamo.objects.select_related('id_cliente').all()
    serializer_class = HistorialPrestamoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    search_fields = ['numero_prestamo', 'id_cliente__nombre', 'producto']
    filterset_fields = ['id_cliente', 'numero_prestamo']
    ordering_fields = ['id_historial', 'monto', 'saldo']
