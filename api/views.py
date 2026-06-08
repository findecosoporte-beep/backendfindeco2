"""ViewSets de la API de prestamos."""

import io
import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
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
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    UsuarioSerializer,
    ZonaSerializer,
)

AUTH_PERMISSION_CLASSES = (RoleBasedAccessPermission,)
CENTS = Decimal('0.01')
_WEEKDAY_ES = ('lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom')


def _extract_cuota_numero_documento(documento: str | None) -> int | None:
    """Replica la lógica de PagoSerializer para cruzar documento 'Cuota N' con PrestamoCuota."""
    m = re.search(r'cuota\s*(\d+)', (documento or '').strip(), flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _titulo_columna_cuota_sem(d):
    """Encabezado corto tipo libreta: «lun 07/04»."""
    wd = _WEEKDAY_ES[d.weekday()]
    return f'{wd}. {d.day:02d}/{d.month:02d}'


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _frecuencia_anual(forma_pago: str) -> int:
    return {'mensual': 12, 'quincenal': 24, 'semanal': 52}[forma_pago]


def _periodic_rate_from_nominal(tasa_nominal_pct: Decimal, forma_pago: str) -> Decimal:
    """Convierte tasa nominal mensual (%) a tasa por periodo."""
    if forma_pago == 'semanal':
        return tasa_nominal_pct / Decimal('4')
    if forma_pago == 'quincenal':
        return tasa_nominal_pct / Decimal('2')
    return tasa_nominal_pct


def _periods_from_months(plazo_meses: int, forma_pago: str) -> int:
    """Convierte plazo en meses al número de cuotas/periodos."""
    if forma_pago == 'semanal':
        return plazo_meses * 4
    if forma_pago == 'quincenal':
        return plazo_meses * 2
    return plazo_meses


def _annual_rate_from_nominal(tasa_nominal_pct: Decimal) -> Decimal:
    """Calcula la tasa anual efectiva desde una tasa nominal mensual."""
    tasa_nominal = tasa_nominal_pct / Decimal('100')
    tasa_anual = (Decimal('1') + tasa_nominal) ** 12 - Decimal('1')
    return tasa_anual * Decimal('100')


def _build_pago_invoice_pdf(pago: Pago, ticket_format: str = '58') -> bytes:
    """Genera un PDF de factura con estilo ticket (58mm u 80mm)."""
    buffer = io.BytesIO()
    is_80mm = ticket_format == '80'
    ticket_w = (80 if is_80mm else 58) * mm
    ticket_h = 210 * mm
    pdf = canvas.Canvas(buffer, pagesize=(ticket_w, ticket_h))
    width, height = ticket_w, ticket_h

    cliente = pago.id_prestamo.id_cliente
    capital = _round_money(Decimal(pago.capital))
    interes = _round_money(Decimal(pago.interes))
    mora = _round_money(Decimal(pago.mora))
    subtotal = _round_money(capital + interes)
    total_pagado = _round_money(subtotal + mora)

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
    unit_price = _round_money(total_pagado)
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


class MeView(APIView):
    """Perfil del usuario JWT y vínculo con tabla operativa `usuarios`."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        """Retorna el perfil del usuario autenticado y su rol operativo vinculado."""
        user = request.user
        actor = (
            Usuario.objects.filter(correo=user.email)
            .only('id_usuario', 'nombre', 'rol', 'correo')
            .first()
        )
        return Response(
            {
                'username': user.get_username(),
                'email': user.email or '',
                'vinculado': actor is not None,
                'rol': actor.rol if actor else None,
                'nombre_operativo': actor.nombre if actor else None,
                'id_usuario': actor.id_usuario if actor else None,
            }
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
        tasa_anual_pct = _annual_rate_from_nominal(tasa_nominal_pct)
        tasa_periodica = _periodic_rate_from_nominal(tasa_nominal_pct, forma_pago) / Decimal('100')
        comision_pct = Decimal(data['comision']) / Decimal('100')

        frecuencia = _frecuencia_anual(forma_pago)
        periodos = _periods_from_months(plazo_meses, forma_pago)
        capital_fijo = _round_money(monto / Decimal(periodos))
        interes_fijo = _round_money(monto * tasa_periodica)
        cuota = _round_money(capital_fijo + interes_fijo)
        saldo = monto
        amortizacion = []
        total_interes = Decimal('0.00')

        for periodo in range(1, periodos + 1):
            interes = interes_fijo
            capital = capital_fijo
            cuota_final = cuota

            if periodo == periodos:
                capital = saldo
                cuota_final = _round_money(capital + interes)

            saldo = _round_money(saldo - capital)
            if saldo < 0:
                saldo = Decimal('0.00')
            total_interes += interes

            amortizacion.append(
                {
                    'periodo': periodo,
                    'cuota': float(cuota_final),
                    'capital': float(_round_money(capital)),
                    'interes': float(interes),
                    'saldo': float(saldo),
                }
            )

        total_interes = _round_money(total_interes)
        comision_monto = _round_money(monto * comision_pct)
        total_pagar = _round_money(monto + total_interes + comision_monto)

        return Response(
            {
                'monto': float(_round_money(monto)),
                'plazo': periodos,
                'forma_pago': forma_pago,
                'tasa_interes': float(data['tasa_interes']),
                'tasa_anual': float(_round_money(tasa_anual_pct)),
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
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor')
    search_fields = ['dni', 'telefono', 'nombre']
    filterset_fields = ['id_cliente', 'dni']
    ordering_fields = ['id_cliente', 'nombre']

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
    required_write_roles = ('administrador', 'supervisor', 'asesor', 'cobranza_adm_jud')
    filterset_fields = ['id_cliente']
    ordering_fields = ['creado_en', 'id_documento']


class ContratoPrestamoViewSet(viewsets.ModelViewSet):
    """Gestión de contratos de préstamo editables por cliente."""

    queryset = ContratoPrestamo.objects.select_related('id_cliente', 'id_prestamo', 'id_documento').all()
    serializer_class = ContratoPrestamoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor', 'asesor')
    filterset_fields = ['id_cliente', 'id_prestamo', 'id_documento', 'actor']
    ordering_fields = ['creado_en', 'actualizado_en', 'id_contrato']


class UsuarioViewSet(viewsets.ModelViewSet):
    """Consulta y alta de usuarios operativos (POST: registro de asesor con cuenta Django)."""

    queryset = Usuario.objects.all()
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor')
    http_method_names = ['get', 'head', 'options', 'post']
    serializer_class = UsuarioSerializer
    search_fields = ['nombre', 'correo', 'rol']
    filterset_fields = ['rol']
    ordering_fields = ['id_usuario', 'nombre']

    def get_serializer_class(self):
        if self.action == 'create':
            return UsuarioAsesorCreateSerializer
        return UsuarioSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        return Response(UsuarioSerializer(usuario).data, status=status.HTTP_201_CREATED)


class ZonaViewSet(viewsets.ModelViewSet):
    """Catálogo de zonas territoriales (lectura y alta con día de semana)."""

    queryset = Zona.objects.all()
    serializer_class = ZonaSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor')
    search_fields = ['nombre', 'codigo']
    ordering_fields = ['id_zona', 'nombre', 'codigo', 'dia_semana']


class CarteraViewSet(viewsets.ModelViewSet):
    """CRUD de carteras operativas (nombre y día de cobro)."""

    queryset = Cartera.objects.all()
    serializer_class = CarteraSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor')
    search_fields = ['nombre', 'dia_cobro']
    ordering_fields = ['id_cartera', 'nombre', 'dia_cobro']


class PrestamoViewSet(viewsets.ModelViewSet):
    """CRUD de prestamos con filtros de negocio."""

    queryset = Prestamo.objects.select_related('id_cliente', 'id_usuario', 'id_zona').all()
    serializer_class = PrestamoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor')
    search_fields = ['numero_prestamo', 'id_cliente__nombre', 'producto', 'estado']
    filterset_fields = [
        'estado',
        'forma_pago',
        'id_cliente',
        'id_usuario',
        'numero_prestamo',
        'id_zona',
        'fecha_entrega',
        'fecha_vencimiento',
    ]
    ordering_fields = ['id_prestamo', 'monto', 'fecha_vencimiento', 'dias_mora']

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

        id_cliente_param = (request.query_params.get('id_cliente') or '').strip()
        if id_cliente_param.isdigit():
            qs = qs.filter(id_cliente_id=int(id_cliente_param))

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

        prestamos = list(qs.order_by('numero_prestamo'))
        ids = [p.id_prestamo for p in prestamos]

        primera_cuota: dict[int, Decimal] = {}
        cuotas_por_prestamo: dict[int, list[PrestamoCuota]] = defaultdict(list)
        for c in (
            PrestamoCuota.objects.filter(id_prestamo_id__in=ids)
            .order_by('id_prestamo_id', 'numero_cuota')
            .only(
                'id_prestamo_id',
                'total_programado',
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

        cuotas_pagadas_nums: dict[int, set[int]] = defaultdict(set)
        for pg in (
            Pago.objects.filter(id_prestamo_id__in=ids)
            .only('id_prestamo_id', 'documento')
            .iterator()
        ):
            n = _extract_cuota_numero_documento(pg.documento)
            if n is not None:
                cuotas_pagadas_nums[pg.id_prestamo_id].add(n)

        ultimo_pago_por: dict[int, Pago] = {}
        for pay in (
            Pago.objects.filter(id_prestamo_id__in=ids)
            .order_by('id_prestamo_id', '-fecha_pago', '-id_pago')
            .only('id_prestamo_id', 'saldo', 'fecha_pago', 'id_pago')
        ):
            if pay.id_prestamo_id not in ultimo_pago_por:
                ultimo_pago_por[pay.id_prestamo_id] = pay

        clientes_ids: set[int] = set()
        sum_inicial = Decimal('0')
        sum_actual = Decimal('0')
        sum_plazo = 0

        filas: list[dict] = []
        for p in prestamos:
            clientes_ids.add(p.id_cliente_id)
            monto = _round_money(Decimal(p.monto))
            cuota_pl = _round_money(
                Decimal(primera_cuota.get(p.id_prestamo, monto)),
            )

            ult = ultimo_pago_por.get(p.id_prestamo)
            if ult is not None:
                saldo_act = _round_money(Decimal(ult.saldo))
            else:
                saldo_act = monto

            asesor_txt = (p.asesor or '').strip()
            if not asesor_txt and p.id_usuario_id:
                asesor_txt = (getattr(p.id_usuario, 'nombre', None) or '').strip()

            plan_rows = cuotas_por_prestamo.get(p.id_prestamo, [])
            paid_nums = cuotas_pagadas_nums.get(p.id_prestamo, set())
            siguiente = next((row for row in plan_rows if row.numero_cuota not in paid_nums), None)

            sig_fields: dict = {
                'cuota_siguiente_numero': None,
                'cuota_siguiente_fecha': None,
                'cuota_siguiente_monto': None,
                'cuota_siguiente_capital': None,
                'cuota_siguiente_interes': None,
                'cuota_siguiente_saldo_capital': None,
            }
            if siguiente is not None:
                sig_fields = {
                    'cuota_siguiente_numero': siguiente.numero_cuota,
                    'cuota_siguiente_fecha': siguiente.fecha_programada.isoformat(),
                    'cuota_siguiente_monto': str(_round_money(Decimal(siguiente.total_programado))),
                    'cuota_siguiente_capital': str(_round_money(Decimal(siguiente.capital_programado))),
                    'cuota_siguiente_interes': str(_round_money(Decimal(siguiente.interes_programado))),
                    'cuota_siguiente_saldo_capital': str(
                        _round_money(Decimal(siguiente.saldo_capital_programado))
                    ),
                }

            row_data = {
                'id_prestamo': p.id_prestamo,
                'numero_prestamo': p.numero_prestamo,
                'nombre_cliente': p.id_cliente.nombre,
                'fecha_entrega': p.fecha_entrega.isoformat(),
                'fecha_vencimiento': p.fecha_vencimiento.isoformat(),
                'dias_mora': int(p.dias_mora or 0),
                'saldo_inicial': str(monto),
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
            filas.append(row_data)

            sum_inicial += monto
            sum_actual += saldo_act
            sum_plazo += int(p.plazo or 0)

        resumen = {
            'clientes_distintos': len(clientes_ids),
            'prestamos': len(prestamos),
            'total_cuotas_plazo': sum_plazo,
            'total_saldo_inicial': str(_round_money(sum_inicial)),
            'total_saldo_actual': str(_round_money(sum_actual)),
        }

        return Response(
            {
                'fecha_reporte': timezone.localdate().isoformat(),
                'filas': filas,
                'resumen': resumen,
            }
        )

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


class PagoViewSet(viewsets.ModelViewSet):
    """CRUD de pagos asociados a prestamos."""

    queryset = Pago.objects.select_related('id_prestamo').all()
    serializer_class = PagoSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor', 'asesor', 'cobranza_adm_jud')
    search_fields = ['documento']
    filterset_fields = {
        'id_prestamo': ['exact'],
        'fecha_pago': ['exact', 'gte', 'lte'],
    }
    ordering_fields = ['id_pago', 'fecha_pago']

    @action(detail=False, methods=['get'], url_path='hoja-semanal-cuotas')
    def hoja_semanal_cuotas(self, request):
        """Cuadrícula fecha de cuota × préstamos semanales (para registrar pagos por semana/fecha).

        Query: ``fecha_cuota_desde``, ``fecha_cuota_hasta`` obligatorios (YYYY-MM-DD);
        opcional ``id_zona`` para filtrar territorio operativo del préstamo.
        """
        fd_raw = (request.query_params.get('fecha_cuota_desde') or '').strip()
        fh_raw = (request.query_params.get('fecha_cuota_hasta') or '').strip()
        d_desde = parse_date(fd_raw) if fd_raw else None
        d_hasta = parse_date(fh_raw) if fh_raw else None
        if not d_desde or not d_hasta:
            return Response(
                {'detail': 'fecha_cuota_desde y fecha_cuota_hasta son obligatorios (YYYY-MM-DD).'},
                status=400,
            )
        if d_hasta < d_desde:
            return Response({'detail': 'fecha_cuota_hasta no puede ser anterior a fecha_cuota_desde.'}, status=400)
        if (d_hasta - d_desde).days > 366:
            return Response({'detail': 'El intervalo máximo es 367 días.'}, status=400)

        zona_param = (request.query_params.get('id_zona') or '').strip()
        qs = (
            Prestamo.objects.filter(forma_pago='semanal')
            .exclude(estado__in=('pagado', 'cancelado'))
            .select_related('id_cliente', 'id_zona')
            .order_by('numero_prestamo')
        )
        if zona_param.isdigit():
            qs = qs.filter(id_zona_id=int(zona_param))

        prestamos = list(qs)
        prestamos_ids = [p.pk for p in prestamos]

        columnas_dates: list = []
        if prestamos_ids:
            fechas_cuotas = PrestamoCuota.objects.filter(
                id_prestamo_id__in=prestamos_ids,
                fecha_programada__gte=d_desde,
                fecha_programada__lte=d_hasta,
            ).values_list('fecha_programada', flat=True)
            columnas_dates = sorted({d for d in fechas_cuotas})
        max_cols = request.query_params.get('max_columnas')
        limite_cols = min(int(max_cols), 156) if (max_cols or '').strip().isdigit() else 104
        if len(columnas_dates) > limite_cols:
            return Response(
                {
                    'detail': (
                        f'Demasiadas semanas únicas ({len(columnas_dates)} columnas); '
                        f'acierta el intervalo de fechas (límite {limite_cols}) o sube ``max_columnas``.'
                    )
                },
                status=400,
            )

        cuotas_por_pid: dict[int, list] = defaultdict(list)
        if prestamos_ids:
            cuotas_ls = PrestamoCuota.objects.filter(
                id_prestamo_id__in=prestamos_ids,
                fecha_programada__gte=d_desde,
                fecha_programada__lte=d_hasta,
            ).order_by('id_prestamo_id', 'fecha_programada', 'numero_cuota')
            for c in cuotas_ls:
                cuotas_por_pid[c.id_prestamo_id].append(c)

        pagos_por_cuota: dict[tuple[int, int], Pago] = {}
        if prestamos_ids:
            for pg in (
                Pago.objects.filter(id_prestamo_id__in=prestamos_ids).only(
                    'id_prestamo',
                    'documento',
                    'id_pago',
                    'fecha_pago',
                    'capital',
                    'interes',
                    'mora',
                )
            ):
                numero = PagoSerializer._extract_cuota_numero(pg.documento)
                if numero is not None:
                    pagos_por_cuota[(pg.id_prestamo_id, numero)] = pg

        columnas = [
            {'fecha_cuota': d.isoformat(), 'titulo': _titulo_columna_cuota_sem(d)} for d in columnas_dates
        ]

        filas: list[dict] = []
        for prest in prestamos:
            cliente = prest.id_cliente
            nombre_zona = ''
            if prest.id_zona_id:
                nombre_zona = getattr(prest.id_zona, 'nombre', '') or ''

            por_fecha_iso: dict[str, dict | None] = {d.isoformat(): None for d in columnas_dates}

            for c in cuotas_por_pid.get(prest.pk, []):
                key = c.fecha_programada.isoformat()
                if key not in por_fecha_iso:
                    continue
                pago_cu = pagos_por_cuota.get((prest.pk, c.numero_cuota))
                por_fecha_iso[key] = {
                    'id_cuota': c.id_cuota,
                    'numero_cuota': c.numero_cuota,
                    'fecha_programada': c.fecha_programada.isoformat(),
                    'capital_programado': str(_round_money(Decimal(c.capital_programado))),
                    'interes_programado': str(_round_money(Decimal(c.interes_programado))),
                    'total_programado': str(_round_money(Decimal(c.total_programado))),
                    'saldo_capital_programado': str(_round_money(Decimal(c.saldo_capital_programado))),
                    'estado_cuota': c.estado,
                    'pagado': pago_cu is not None,
                    'fecha_pago': pago_cu.fecha_pago.isoformat() if pago_cu else None,
                    'id_pago': pago_cu.id_pago if pago_cu else None,
                }

            filas.append(
                {
                    'id_prestamo': prest.pk,
                    'numero_prestamo': prest.numero_prestamo,
                    'id_cliente': cliente.pk if cliente else None,
                    'nombre_cliente': cliente.nombre if cliente else '',
                    'dni_cliente': cliente.dni if cliente else '',
                    'id_zona': prest.id_zona_id,
                    'nombre_zona': nombre_zona,
                    'estado_prestamo': prest.estado,
                    'cuotas': por_fecha_iso,
                },
            )

        return Response({'columnas': columnas, 'filas': filas})

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
    required_write_roles = ('administrador', 'supervisor')
    filterset_fields = ['id_prestamo', 'numero_cuota', 'estado', 'fecha_programada']
    ordering_fields = ['id_cuota', 'numero_cuota', 'fecha_programada']


class ServicioViewSet(viewsets.ModelViewSet):
    """CRUD de servicios financieros por prestamo."""

    queryset = Servicio.objects.select_related('id_prestamo').all()
    serializer_class = ServicioSerializer
    permission_classes = AUTH_PERMISSION_CLASSES
    required_write_roles = ('administrador', 'supervisor')
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
