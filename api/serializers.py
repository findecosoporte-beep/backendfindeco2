"""Serializers de la API de prestamos."""

import calendar
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import (
    Cartera,
    Cliente,
    ClienteDocumento,
    ContratoPrestamo,
    HistorialPrestamo,
    Pago,
    Prestamo,
    PrestamoCuota,
    Servicio,
    Usuario,
    Zona,
)

CENTS = Decimal('0.01')


def sync_cartera_desde_zona(zona: Zona) -> None:
    """Crea, actualiza o elimina la cartera ligada a una zona según `dia_semana`."""
    if not zona.dia_semana:
        Cartera.objects.filter(zona=zona).delete()
        return
    Cartera.objects.update_or_create(
        zona=zona,
        defaults={'nombre': zona.nombre, 'dia_cobro': zona.dia_semana},
    )


def _add_months(base_date: date, months: int) -> date:
    """Suma meses preservando día válido dentro del mes destino."""
    month_index = (base_date.month - 1) + months
    year = base_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _calculate_fecha_vencimiento(fecha_entrega: date, plazo: int, forma_pago: str) -> date:
    """Calcula fecha de vencimiento usando plazo en meses."""
    if forma_pago == 'semanal':
        return fecha_entrega + timedelta(days=plazo * 4 * 7)
    if forma_pago == 'quincenal':
        return fecha_entrega + timedelta(days=plazo * 2 * 15)
    return _add_months(fecha_entrega, plazo)


def _calculate_fecha_cuota(fecha_entrega: date, periodo: int, forma_pago: str) -> date:
    """Calcula la fecha programada de cuota según periodicidad."""
    if forma_pago == 'semanal':
        return fecha_entrega + timedelta(days=periodo * 7)
    if forma_pago == 'quincenal':
        return fecha_entrega + timedelta(days=periodo * 15)
    return _add_months(fecha_entrega, periodo)


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


class ClienteSerializer(serializers.ModelSerializer):
    """Serializer para la entidad Cliente."""

    class Meta:
        model = Cliente
        fields = '__all__'


class UsuarioSerializer(serializers.ModelSerializer):
    """Serializer de lectura para usuarios del sistema."""

    class Meta:
        model = Usuario
        fields = ('id_usuario', 'nombre', 'rol', 'correo')


class UsuarioAsesorCreateSerializer(serializers.ModelSerializer):
    """Alta de asesor: crea usuario Django (acceso) y fila operativa `Usuario` con rol asesor."""

    password = serializers.CharField(write_only=True, min_length=8, max_length=128)

    class Meta:
        model = Usuario
        fields = ('nombre', 'correo', 'password')

    def validate_nombre(self, value: str) -> str:
        t = (value or '').strip()
        if not t:
            raise serializers.ValidationError('El nombre es obligatorio.')
        return t

    def validate_correo(self, value: str) -> str:
        v = (value or '').strip().lower()
        if not v:
            raise serializers.ValidationError('El correo es obligatorio.')
        if Usuario.objects.filter(correo__iexact=v).exists():
            raise serializers.ValidationError('Ya existe un perfil operativo con este correo.')
        UserModel = get_user_model()
        if UserModel.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError('Ya existe una cuenta de acceso con este correo.')
        return v

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        nombre = validated_data['nombre']
        correo = validated_data['correo']
        UserModel = get_user_model()
        UserModel.objects.create_user(username=correo, email=correo, password=password)
        return Usuario.objects.create(
            nombre=nombre,
            correo=correo,
            rol='asesor',
            clave='legacy-operativo',
        )


class ZonaSerializer(serializers.ModelSerializer):
    """Catálogo de zonas territoriales."""

    class Meta:
        model = Zona
        fields = ('id_zona', 'codigo', 'nombre', 'dia_semana')

    @transaction.atomic
    def create(self, validated_data):
        inst = super().create(validated_data)
        sync_cartera_desde_zona(inst)
        return inst

    @transaction.atomic
    def update(self, instance, validated_data):
        inst = super().update(instance, validated_data)
        sync_cartera_desde_zona(inst)
        return inst


class CarteraSerializer(serializers.ModelSerializer):
    """Carteras operativas (nombre y día de cobro)."""

    id_zona = serializers.IntegerField(source='zona_id', read_only=True, allow_null=True)

    class Meta:
        model = Cartera
        fields = ('id_cartera', 'nombre', 'dia_cobro', 'id_zona')


class PrestamoSerializer(serializers.ModelSerializer):
    """Serializer para prestamos con validaciones de negocio."""

    zona = ZonaSerializer(source='id_zona', read_only=True)

    class Meta:
        model = Prestamo
        fields = '__all__'

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        monto = attrs.get('monto', getattr(instance, 'monto', None))
        tasa_interes = attrs.get('tasa_interes', getattr(instance, 'tasa_interes', None))
        plazo = attrs.get('plazo', getattr(instance, 'plazo', None))
        comision = attrs.get('comision', getattr(instance, 'comision', None))
        fecha_entrega = attrs.get('fecha_entrega', getattr(instance, 'fecha_entrega', None))
        forma_pago = attrs.get('forma_pago', getattr(instance, 'forma_pago', None))

        if 'id_zona' in attrs:
            zona_val = attrs['id_zona']
            if zona_val is not None:
                attrs['sucursal'] = zona_val.nombre
            elif instance is None:
                attrs['sucursal'] = attrs.get('sucursal')
            else:
                attrs['sucursal'] = None

        if monto is not None and monto < 0:
            raise serializers.ValidationError('El monto no puede ser negativo.')
        if tasa_interes is not None and tasa_interes < 0:
            raise serializers.ValidationError('La tasa de interes no puede ser negativa.')
        if plazo is not None and plazo <= 0:
            raise serializers.ValidationError('El plazo debe ser mayor a cero.')
        if comision is not None and comision < 0:
            raise serializers.ValidationError('La comision no puede ser negativa.')
        if fecha_entrega is not None and plazo is not None and forma_pago is not None:
            attrs['fecha_vencimiento'] = _calculate_fecha_vencimiento(fecha_entrega, int(plazo), forma_pago)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        prestamo = super().create(validated_data)

        monto = Decimal(prestamo.monto)
        plazo_meses = int(prestamo.plazo)
        periodos = _periods_from_months(plazo_meses, prestamo.forma_pago)
        tasa_nominal_pct = Decimal(prestamo.tasa_interes)
        tasa_periodica = _periodic_rate_from_nominal(tasa_nominal_pct, prestamo.forma_pago) / Decimal('100')
        capital_fijo = (monto / Decimal(periodos)).quantize(CENTS, rounding=ROUND_HALF_UP)
        interes_fijo = (monto * tasa_periodica).quantize(CENTS, rounding=ROUND_HALF_UP)
        cuota_periodica = (capital_fijo + interes_fijo).quantize(CENTS, rounding=ROUND_HALF_UP)
        fecha_entrega = prestamo.fecha_entrega
        forma_pago = prestamo.forma_pago

        saldo_capital = monto
        cuotas: list[PrestamoCuota] = []

        for periodo in range(1, periodos + 1):
            interes = interes_fijo
            capital = capital_fijo
            total = cuota_periodica

            if periodo == periodos:
                capital = saldo_capital
                total = (capital + interes).quantize(CENTS, rounding=ROUND_HALF_UP)

            saldo_capital = (saldo_capital - capital).quantize(CENTS, rounding=ROUND_HALF_UP)
            if saldo_capital < 0:
                saldo_capital = Decimal('0.00')

            cuotas.append(
                PrestamoCuota(
                    id_prestamo=prestamo,
                    numero_cuota=periodo,
                    fecha_programada=_calculate_fecha_cuota(fecha_entrega, periodo, forma_pago),
                    capital_programado=capital,
                    interes_programado=interes,
                    servicios_programado=Decimal('0.00'),
                    otros_programado=Decimal('0.00'),
                    total_programado=total,
                    saldo_capital_programado=saldo_capital,
                    estado='pendiente',
                )
            )

        PrestamoCuota.objects.bulk_create(cuotas)
        return prestamo


class SimulacionPrestamoSerializer(serializers.Serializer):
    """Entrada para simular cuota y tabla de amortizacion."""

    monto = serializers.DecimalField(max_digits=12, decimal_places=2)
    plazo = serializers.IntegerField(min_value=1)
    tasa_interes = serializers.DecimalField(max_digits=5, decimal_places=2)
    forma_pago = serializers.ChoiceField(choices=('mensual', 'quincenal', 'semanal'))
    comision = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal('0.00'))

    def validate(self, attrs):
        if attrs['monto'] <= 0:
            raise serializers.ValidationError('El monto debe ser mayor a cero.')
        if attrs['tasa_interes'] < 0:
            raise serializers.ValidationError('La tasa de interes no puede ser negativa.')
        if attrs['comision'] < 0:
            raise serializers.ValidationError('La comision no puede ser negativa.')
        return attrs


class PagoSerializer(serializers.ModelSerializer):
    """Serializer para pagos con validacion de montos no negativos."""

    class Meta:
        model = Pago
        fields = '__all__'

    @staticmethod
    def _extract_cuota_numero(documento: str | None) -> int | None:
        cuota_match = re.search(r'cuota\s*(\d+)', (documento or '').strip(), flags=re.IGNORECASE)
        if not cuota_match:
            return None
        return int(cuota_match.group(1))

    def _validate_cuota_duplicate(self, prestamo: Prestamo, cuota_numero: int, instance_pk: int | None = None) -> None:
        duplicate_qs = Pago.objects.filter(id_prestamo=prestamo)
        if instance_pk is not None:
            duplicate_qs = duplicate_qs.exclude(pk=instance_pk)
        for existing_pago in duplicate_qs.only('id_pago', 'documento'):
            existing_cuota = self._extract_cuota_numero(existing_pago.documento)
            if existing_cuota == cuota_numero:
                raise serializers.ValidationError(
                    f'La cuota {cuota_numero} ya fue registrada para este prestamo.'
                )

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        prestamo = attrs.get('id_prestamo', getattr(instance, 'id_prestamo', None))
        documento = attrs.get('documento', getattr(instance, 'documento', None))

        for field_name in ('capital', 'interes', 'mora', 'saldo'):
            value = attrs.get(field_name, getattr(instance, field_name, None))
            if value is not None and value < 0:
                raise serializers.ValidationError(f'El campo {field_name} no puede ser negativo.')

        cuota_numero = self._extract_cuota_numero(documento)
        if prestamo is not None and cuota_numero is not None:
            self._validate_cuota_duplicate(
                prestamo=prestamo,
                cuota_numero=cuota_numero,
                instance_pk=instance.pk if instance is not None else None,
            )
        return attrs

    @staticmethod
    def _sync_prestamo_state(prestamo: Prestamo, pago: Pago) -> None:
        """Actualiza estado y dias de mora del prestamo en base al pago."""
        saldo = Decimal(pago.saldo)
        mora = Decimal(pago.mora)
        dias_mora = 0
        if pago.fecha_pago and prestamo.fecha_vencimiento and pago.fecha_pago > prestamo.fecha_vencimiento:
            dias_mora = (pago.fecha_pago - prestamo.fecha_vencimiento).days

        if saldo <= 0:
            prestamo.estado = 'pagado'
            prestamo.dias_mora = 0
        elif mora > 0 or dias_mora > 0:
            prestamo.estado = 'mora'
            prestamo.dias_mora = max(dias_mora, prestamo.dias_mora)
        else:
            prestamo.estado = 'activo'
            prestamo.dias_mora = 0

        prestamo.save(update_fields=['estado', 'dias_mora'])

    @transaction.atomic
    def create(self, validated_data):
        prestamo = validated_data.get('id_prestamo')
        documento = validated_data.get('documento')
        cuota_numero = self._extract_cuota_numero(documento)
        if prestamo is not None and cuota_numero is not None:
            # Lock del prestamo para serializar altas de pagos concurrentes por la misma cuota.
            Prestamo.objects.select_for_update().get(pk=prestamo.pk)
            self._validate_cuota_duplicate(prestamo=prestamo, cuota_numero=cuota_numero)
        pago = super().create(validated_data)
        self._sync_prestamo_state(pago.id_prestamo, pago)
        return pago

    @transaction.atomic
    def update(self, instance, validated_data):
        prestamo = validated_data.get('id_prestamo', instance.id_prestamo)
        documento = validated_data.get('documento', instance.documento)
        cuota_numero = self._extract_cuota_numero(documento)
        if prestamo is not None and cuota_numero is not None:
            Prestamo.objects.select_for_update().get(pk=prestamo.pk)
            self._validate_cuota_duplicate(
                prestamo=prestamo,
                cuota_numero=cuota_numero,
                instance_pk=instance.pk,
            )
        pago = super().update(instance, validated_data)
        self._sync_prestamo_state(pago.id_prestamo, pago)
        return pago


class PrestamoCuotaSerializer(serializers.ModelSerializer):
    """Serializer para plan de pagos por cuota persistido."""

    class Meta:
        model = PrestamoCuota
        fields = '__all__'

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        numero_cuota = attrs.get('numero_cuota', getattr(instance, 'numero_cuota', None))
        if numero_cuota is not None and numero_cuota <= 0:
            raise serializers.ValidationError('El numero de cuota debe ser mayor a cero.')

        for field_name in (
            'capital_programado',
            'interes_programado',
            'servicios_programado',
            'otros_programado',
            'total_programado',
            'saldo_capital_programado',
        ):
            value = attrs.get(field_name, getattr(instance, field_name, None))
            if value is not None and value < 0:
                raise serializers.ValidationError(f'El campo {field_name} no puede ser negativo.')
        return attrs


class ServicioSerializer(serializers.ModelSerializer):
    """Serializer para servicios asociados a un prestamo."""

    class Meta:
        model = Servicio
        fields = '__all__'

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        for field_name in ('inicial', 'descuento', 'abono', 'porcentaje'):
            value = attrs.get(field_name, getattr(instance, field_name, None))
            if value is not None and value < 0:
                raise serializers.ValidationError(f'El campo {field_name} no puede ser negativo.')
        return attrs


class HistorialPrestamoSerializer(serializers.ModelSerializer):
    """Serializer de solo datos para historial de prestamos."""

    class Meta:
        model = HistorialPrestamo
        fields = '__all__'


class ClienteDocumentoSerializer(serializers.ModelSerializer):
    """Serializer para documentos y actividad asociada a clientes."""

    archivo_url = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField(source='creado_en', read_only=True)
    title = serializers.CharField(source='nombre_archivo', read_only=True)
    description = serializers.CharField(source='descripcion', read_only=True)

    class Meta:
        model = ClienteDocumento
        fields = (
            'id_documento',
            'id_cliente',
            'archivo',
            'archivo_url',
            'nombre_archivo',
            'sha256',
            'descripcion',
            'actor',
            'creado_en',
            'timestamp',
            'title',
            'description',
        )
        read_only_fields = ('nombre_archivo', 'sha256', 'creado_en')

    def get_archivo_url(self, obj):
        request = self.context.get('request')
        if not obj.archivo:
            return None
        url = obj.archivo.url
        return request.build_absolute_uri(url) if request else url

    def create(self, validated_data):
        archivo = validated_data.get('archivo')
        validated_data['nombre_archivo'] = getattr(archivo, 'name', 'documento.pdf')
        if archivo is not None:
            digest = hashlib.sha256()
            for chunk in archivo.chunks():
                digest.update(chunk)
            validated_data['sha256'] = digest.hexdigest()
            try:
                archivo.seek(0)
            except (AttributeError, OSError):
                pass
        return super().create(validated_data)


class ContratoPrestamoSerializer(serializers.ModelSerializer):
    """Serializer para contratos guardados y editables por cliente."""

    class Meta:
        model = ContratoPrestamo
        fields = '__all__'
        read_only_fields = ('creado_en', 'actualizado_en')

    def validate_contenido(self, value: str) -> str:
        # Validamos usando una versión normalizada, pero devolvemos el texto original
        # para no alterar formato ni saltos de línea del contrato cargado por el usuario.
        content = (value or '').strip()
        if not content:
            raise serializers.ValidationError('El contenido del contrato no puede quedar vacío.')

        normalized = content.upper()
        required_sections = (
            'CONTRATO DE PRESTAMO',
            'DECLARACIONES',
            'CLAUSULAS',
        )
        missing_sections = [section for section in required_sections if section not in normalized]
        if missing_sections:
            raise serializers.ValidationError(
                f'El contrato está incompleto. Faltan secciones obligatorias: {", ".join(missing_sections)}.'
            )

        required_clauses = ('PRIMERA', 'SEGUNDA', 'TERCERA')
        missing_clauses = [clause for clause in required_clauses if clause not in normalized]
        if missing_clauses:
            raise serializers.ValidationError(
                f'El contrato debe incluir al menos las cláusulas base: {", ".join(missing_clauses)}.'
            )

        if 'PRESTATARIO' not in normalized or 'PRESTAMISTA' not in normalized:
            raise serializers.ValidationError(
                'El contrato debe identificar claramente a PRESTATARIO y PRESTAMISTA.'
            )

        return value


