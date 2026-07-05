"""Serializers de la API de prestamos."""

import hashlib
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers

from .cobrador_scope import validar_cobro_por_cartera
from .core.cuotas import extract_cuota_numero_from_documento
from .core.distribucion_pago import (
    CUOTA_PAGADA_TOLERANCIA,
    abonado_por_cuota_desde_pagos,
    cuota_esta_pagada,
    cuotas_cubiertas_por_pago_acumulado,
    distribuir_monto_en_cuotas,
    pendiente_cuota,
    saldo_pendiente_tras_abono,
    total_abonado_prestamo,
)
from .core.facturacion_sar import (
    ErrorFacturacionSAR,
    asignar_numero_factura_sar,
    formatear_numero_factura_sar,
    texto_rango_autorizado,
)
from .core.money import round_money
from .core.prestamo_calc import (
    periodos_desde_plazo,
    tasa_periodica_para_calculo,
    tasa_semanal_negocio,
    tasa_mensual_negocio,
)
from .models import (
    Cartera,
    Cliente,
    ClienteDocumento,
    ConfiguracionFacturacion,
    ContratoPrestamo,
    HistorialPrestamo,
    Pago,
    Prestamo,
    PrestamoCuota,
    Servicio,
    Usuario,
    UsuarioCartera,
    Zona,
)


def sync_cartera_desde_zona(zona: Zona) -> None:
    """Crea, actualiza o elimina la cartera ligada a una zona según `dia_semana`."""
    if not zona.dia_semana:
        Cartera.objects.filter(zona=zona).delete()
        return
    Cartera.objects.update_or_create(
        zona=zona,
        defaults={'nombre': zona.nombre, 'dia_cobro': zona.dia_semana},
    )


def _dia_cobro_operativo(
    cartera: Cartera | None = None,
    cliente: Cliente | None = None,
    zona: Zona | None = None,
) -> str | None:
    """Día de cobro efectivo: cartera → cliente → zona."""
    if cartera is not None:
        dia = (getattr(cartera, 'dia_cobro', None) or '').strip()
        if dia:
            return dia
    if cliente is not None:
        dia = (getattr(cliente, 'dia_cobro_semanal', None) or '').strip()
        if dia:
            return dia
    if zona is not None:
        dia = (getattr(zona, 'dia_semana', None) or '').strip()
        if dia:
            return dia
    return None


def _resolver_cliente_en_attrs(attrs: dict, instance: Prestamo | None = None) -> Cliente | None:
    cliente = attrs.get('id_cliente')
    if cliente is None and instance is not None:
        cliente = getattr(instance, 'id_cliente', None)
    if cliente is None:
        return None
    if isinstance(cliente, Cliente):
        return cliente
    return Cliente.objects.filter(pk=cliente).first()


ESTADOS_PRESTAMO_ACTIVO = frozenset({'activo', 'mora', 'pendiente_aprobacion'})


def _validar_cliente_para_nuevo_prestamo(cliente: Cliente) -> None:
    """Solo un préstamo abierto por cliente; renovación si los anteriores están cerrados."""
    activos = Prestamo.objects.filter(id_cliente=cliente, estado__in=ESTADOS_PRESTAMO_ACTIVO)
    if not activos.exists():
        return
    numeros = ', '.join(activos.values_list('numero_prestamo', flat=True)[:3])
    raise serializers.ValidationError(
        {
            'id_cliente': (
                f'El cliente tiene un préstamo activo o pendiente ({numeros}). '
                'Debe estar pagado o cancelado para registrar uno nuevo con otro código.'
            )
        }
    )


def _ciclos_para_renovacion(cliente: Cliente) -> int:
    """Ciclo 0 en el primer préstamo; en renovación, máximo histórico + 1."""
    previos = Prestamo.objects.filter(id_cliente=cliente)
    if not previos.exists():
        return 0
    max_ciclos = previos.aggregate(m=Max('ciclos'))['m'] or 0
    return int(max_ciclos) + 1


class ClienteSerializer(serializers.ModelSerializer):
    """Serializer para la entidad Cliente."""

    total_prestamos = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = '__all__'

    def get_total_prestamos(self, obj: Cliente) -> int:
        count = getattr(obj, 'prestamos_count', None)
        if count is not None:
            return int(count)
        return obj.prestamo_set.count()


class UsuarioSerializer(serializers.ModelSerializer):
    """Serializer de lectura para usuarios del sistema."""

    carteras = serializers.SerializerMethodField()
    carteras_detalle = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ('id_usuario', 'nombre', 'rol', 'correo', 'carteras', 'carteras_detalle')

    def get_carteras(self, obj: Usuario) -> list[int]:
        if obj.rol != 'cobrador':
            return []
        return list(
            UsuarioCartera.objects.filter(id_usuario=obj).values_list('id_cartera_id', flat=True)
        )

    def get_carteras_detalle(self, obj: Usuario) -> list[dict]:
        if obj.rol != 'cobrador':
            return []
        return [
            {
                'id_cartera': row.id_cartera_id,
                'nombre': row.id_cartera.nombre,
                'dia_cobro': row.id_cartera.dia_cobro,
            }
            for row in UsuarioCartera.objects.filter(id_usuario=obj).select_related('id_cartera')
        ]


def _validar_carteras_para_cobrador(cartera_ids: list[int], usuario_pk: int | None = None) -> list[int]:
    ids = sorted({int(i) for i in cartera_ids})
    if not ids:
        raise serializers.ValidationError({'carteras': 'Debe asignar al menos una cartera.'})
    encontradas = Cartera.objects.filter(id_cartera__in=ids).count()
    if encontradas != len(ids):
        raise serializers.ValidationError({'carteras': 'Una o más carteras no existen.'})
    ocupadas_qs = UsuarioCartera.objects.filter(id_cartera_id__in=ids).select_related('id_cartera')
    if usuario_pk is not None:
        ocupadas_qs = ocupadas_qs.exclude(id_usuario_id=usuario_pk)
    nombres_ocupadas = [row.id_cartera.nombre for row in ocupadas_qs]
    if nombres_ocupadas:
        raise serializers.ValidationError(
            {'carteras': f'Carteras ya asignadas a otro cobrador: {", ".join(nombres_ocupadas)}.'}
        )
    return ids


def _sync_carteras_cobrador(usuario: Usuario, cartera_ids: list[int]) -> None:
    UsuarioCartera.objects.filter(id_usuario=usuario).delete()
    UsuarioCartera.objects.bulk_create(
        [UsuarioCartera(id_usuario=usuario, id_cartera_id=cid) for cid in cartera_ids]
    )


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


class UsuarioAsesorUpdateSerializer(serializers.ModelSerializer):
    """Edición de asesor: actualiza perfil operativo y cuenta Django vinculada."""

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Usuario
        fields = ('nombre', 'correo', 'password')

    def validate(self, attrs):
        if self.instance and self.instance.rol != 'asesor':
            raise serializers.ValidationError('Solo se pueden editar perfiles con rol asesor.')
        return attrs

    def validate_nombre(self, value: str) -> str:
        t = (value or '').strip()
        if not t:
            raise serializers.ValidationError('El nombre es obligatorio.')
        return t

    def validate_correo(self, value: str) -> str:
        v = (value or '').strip().lower()
        if not v:
            raise serializers.ValidationError('El correo es obligatorio.')
        inst = self.instance
        qs = Usuario.objects.filter(correo__iexact=v)
        if inst:
            qs = qs.exclude(pk=inst.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe un perfil operativo con este correo.')
        UserModel = get_user_model()
        user_qs = UserModel.objects.filter(email__iexact=v)
        if inst:
            user_qs = user_qs.exclude(email__iexact=inst.correo)
        if user_qs.exists():
            raise serializers.ValidationError('Ya existe una cuenta de acceso con este correo.')
        return v

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password == '':
            password = None
        old_correo = instance.correo
        instance = super().update(instance, validated_data)
        UserModel = get_user_model()
        auth_user = UserModel.objects.filter(email__iexact=old_correo).first()
        if auth_user:
            if instance.correo != old_correo:
                auth_user.username = instance.correo
                auth_user.email = instance.correo
            if password:
                auth_user.set_password(password)
            auth_user.save()
        return instance


class UsuarioCobradorCreateSerializer(serializers.ModelSerializer):
    """Alta de cobrador con asignación de carteras."""

    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    carteras = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        min_length=1,
    )

    class Meta:
        model = Usuario
        fields = ('nombre', 'correo', 'password', 'carteras')

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

    def validate_carteras(self, value: list[int]) -> list[int]:
        return _validar_carteras_para_cobrador(value)

    @transaction.atomic
    def create(self, validated_data):
        cartera_ids = validated_data.pop('carteras')
        password = validated_data.pop('password')
        nombre = validated_data['nombre']
        correo = validated_data['correo']
        UserModel = get_user_model()
        UserModel.objects.create_user(username=correo, email=correo, password=password)
        usuario = Usuario.objects.create(
            nombre=nombre,
            correo=correo,
            rol='cobrador',
            clave='legacy-operativo',
        )
        _sync_carteras_cobrador(usuario, cartera_ids)
        return usuario


class UsuarioCobradorUpdateSerializer(serializers.ModelSerializer):
    """Edición de cobrador y carteras asignadas."""

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        required=False,
        allow_blank=True,
    )
    carteras = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        min_length=1,
    )

    class Meta:
        model = Usuario
        fields = ('nombre', 'correo', 'password', 'carteras')

    def validate(self, attrs):
        if self.instance and self.instance.rol != 'cobrador':
            raise serializers.ValidationError('Solo se pueden editar perfiles con rol cobrador.')
        return attrs

    def validate_nombre(self, value: str) -> str:
        t = (value or '').strip()
        if not t:
            raise serializers.ValidationError('El nombre es obligatorio.')
        return t

    def validate_correo(self, value: str) -> str:
        v = (value or '').strip().lower()
        if not v:
            raise serializers.ValidationError('El correo es obligatorio.')
        inst = self.instance
        qs = Usuario.objects.filter(correo__iexact=v)
        if inst:
            qs = qs.exclude(pk=inst.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe un perfil operativo con este correo.')
        UserModel = get_user_model()
        user_qs = UserModel.objects.filter(email__iexact=v)
        if inst:
            user_qs = user_qs.exclude(email__iexact=inst.correo)
        if user_qs.exists():
            raise serializers.ValidationError('Ya existe una cuenta de acceso con este correo.')
        return v

    def validate_carteras(self, value: list[int]) -> list[int]:
        usuario_pk = self.instance.pk if self.instance else None
        return _validar_carteras_para_cobrador(value, usuario_pk=usuario_pk)

    @transaction.atomic
    def update(self, instance, validated_data):
        cartera_ids = validated_data.pop('carteras', None)
        password = validated_data.pop('password', None)
        if password == '':
            password = None
        old_correo = instance.correo
        instance = super().update(instance, validated_data)
        if cartera_ids is not None:
            _sync_carteras_cobrador(instance, cartera_ids)
        UserModel = get_user_model()
        auth_user = UserModel.objects.filter(email__iexact=old_correo).first()
        if auth_user:
            if instance.correo != old_correo:
                auth_user.username = instance.correo
                auth_user.email = instance.correo
            if password:
                auth_user.set_password(password)
            auth_user.save()
        return instance


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
    cartera = CarteraSerializer(source='id_cartera', read_only=True)

    class Meta:
        model = Prestamo
        fields = '__all__'
        extra_kwargs = {
            'fecha_vencimiento': {'required': False},
        }

    def _aplicar_cartera_en_attrs(self, attrs: dict) -> dict:
        cartera = attrs.get('id_cartera')
        if cartera is None:
            return attrs
        if getattr(cartera, 'zona_id', None):
            attrs['id_zona'] = cartera.zona
        attrs['sucursal'] = (getattr(cartera, 'nombre', None) or '').strip() or attrs.get('sucursal')
        return attrs

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        if instance is None and not attrs.get('id_cartera'):
            raise serializers.ValidationError({'id_cartera': 'La cartera es obligatoria al crear el préstamo.'})

        if attrs.get('id_cartera'):
            attrs = self._aplicar_cartera_en_attrs(attrs)
        elif 'id_zona' in attrs:
            zona_val = attrs['id_zona']
            if zona_val is not None:
                attrs['sucursal'] = zona_val.nombre
                if instance is None or not getattr(instance, 'id_cartera_id', None):
                    cartera_vinculada = Cartera.objects.filter(zona=zona_val).first()
                    if cartera_vinculada is not None:
                        attrs['id_cartera'] = cartera_vinculada
            elif instance is None:
                attrs['sucursal'] = attrs.get('sucursal')
            else:
                attrs['sucursal'] = None

        monto = attrs.get('monto', getattr(instance, 'monto', None))
        tasa_interes = attrs.get('tasa_interes', getattr(instance, 'tasa_interes', None))
        plazo = attrs.get('plazo', getattr(instance, 'plazo', None))
        comision = attrs.get('comision', getattr(instance, 'comision', None))
        fecha_entrega = attrs.get('fecha_entrega', getattr(instance, 'fecha_entrega', None))
        forma_pago = attrs.get('forma_pago', getattr(instance, 'forma_pago', None))

        if monto is not None and monto < 0:
            raise serializers.ValidationError('El monto no puede ser negativo.')
        if tasa_interes is not None and tasa_interes < 0:
            raise serializers.ValidationError('La tasa de interes no puede ser negativa.')
        if plazo is not None and plazo <= 0:
            raise serializers.ValidationError('El plazo debe ser mayor a cero.')
        if comision is not None and comision < 0:
            raise serializers.ValidationError('La comision no puede ser negativa.')
        if forma_pago == 'semanal' and plazo is not None:
            attrs['tasa_interes'] = tasa_semanal_negocio(int(plazo))
        elif forma_pago == 'mensual' and plazo is not None:
            attrs['tasa_interes'] = tasa_mensual_negocio(int(plazo))
        if fecha_entrega is not None and plazo is not None and forma_pago is not None:
            cartera = attrs.get('id_cartera', getattr(instance, 'id_cartera', None))
            cliente = _resolver_cliente_en_attrs(attrs, instance)
            zona = attrs.get('id_zona', getattr(instance, 'id_zona', None))
            dia_cobro = _dia_cobro_operativo(cartera, cliente, zona)
            attrs['fecha_vencimiento'] = calculate_fecha_vencimiento(
                fecha_entrega,
                int(plazo),
                forma_pago,
                dia_cobro,
            )
        if instance is None:
            cartera = attrs.get('id_cartera')
            cliente = _resolver_cliente_en_attrs(attrs)
            if not _dia_cobro_operativo(cartera, cliente, attrs.get('id_zona')):
                raise serializers.ValidationError(
                    {
                        'id_cartera': (
                            'Selecciona una cartera con día de cobro (p. ej. lunes). '
                            'Las cuotas se programan en ese día de la semana.'
                        )
                    }
                )
            if cliente is not None:
                _validar_cliente_para_nuevo_prestamo(cliente)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        cliente = validated_data.get('id_cliente')
        if cliente is not None:
            validated_data['ciclos'] = _ciclos_para_renovacion(cliente)
        prestamo = super().create(validated_data)

        monto = Decimal(prestamo.monto)
        plazo = int(prestamo.plazo)
        periodos = periodos_desde_plazo(plazo, prestamo.forma_pago)
        tasa_nominal_pct = Decimal(prestamo.tasa_interes)
        tasa_periodica = tasa_periodica_para_calculo(
            tasa_nominal_pct,
            prestamo.forma_pago,
            plazo,
        ) / Decimal('100')
        capital_fijo = round_money(monto / Decimal(periodos))
        interes_fijo = round_money(monto * tasa_periodica)
        cuota_periodica = round_money(capital_fijo + interes_fijo)
        fecha_entrega = prestamo.fecha_entrega
        forma_pago = prestamo.forma_pago
        dia_cobro = _dia_cobro_operativo(
            prestamo.id_cartera if prestamo.id_cartera_id else None,
            prestamo.id_cliente,
            prestamo.id_zona if prestamo.id_zona_id else None,
        )

        saldo_capital = monto
        cuotas: list[PrestamoCuota] = []

        for periodo in range(1, periodos + 1):
            interes = interes_fijo
            capital = capital_fijo
            total = cuota_periodica

            if periodo == periodos:
                capital = saldo_capital
                total = round_money(capital + interes)

            saldo_capital = round_money(saldo_capital - capital)
            if saldo_capital < 0:
                saldo_capital = Decimal('0.00')

            cuotas.append(
                PrestamoCuota(
                    id_prestamo=prestamo,
                    numero_cuota=periodo,
                    fecha_programada=calculate_fecha_cuota(
                        fecha_entrega,
                        periodo,
                        forma_pago,
                        dia_cobro,
                    ),
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

    monto_recibido = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        write_only=True,
        help_text='Monto total cobrado; si excede la cuota, se aplica a las siguientes.',
    )

    class Meta:
        model = Pago
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.distribucion_resumen: list[dict] | None = None

    def _pagos_existentes(self, prestamo: Prestamo, instance_pk: int | None = None):
        qs = Pago.objects.filter(id_prestamo=prestamo, anulado=False)
        if instance_pk is not None:
            qs = qs.exclude(pk=instance_pk)
        return qs

    def _validar_cuota_inicio_abierta(
        self,
        prestamo: Prestamo,
        cuota_numero: int,
        plan_rows: list[PrestamoCuota],
        abonado_previo: dict[int, Decimal],
        abonado_total: Decimal,
    ) -> None:
        fila = next((row for row in plan_rows if row.numero_cuota == cuota_numero), None)
        if fila is None:
            return
        abonado = abonado_previo.get(cuota_numero, Decimal('0.00'))
        if cuota_esta_pagada(abonado, Decimal(fila.total_programado)):
            raise serializers.ValidationError(
                f'La cuota {cuota_numero} ya está pagada en su totalidad.'
            )
        # El cliente pudo haber adelantado varias cuotas de una sola vez (el excedente
        # quedó como abono a capital); si el acumulado ya cubre esta cuota, no se
        # puede volver a cobrar aunque no tenga un pago propio con este número.
        cubiertas = cuotas_cubiertas_por_pago_acumulado(plan_rows, abonado_total)
        if cuota_numero in cubiertas:
            raise serializers.ValidationError(
                f'La cuota {cuota_numero} ya está cubierta por abonos anteriores del cliente.'
            )

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        prestamo = attrs.get('id_prestamo', getattr(instance, 'id_prestamo', None))
        documento = attrs.get('documento', getattr(instance, 'documento', None))

        for field_name in ('capital', 'interes', 'mora', 'saldo'):
            value = attrs.get(field_name, getattr(instance, field_name, None))
            if value is not None and value < 0:
                raise serializers.ValidationError(f'El campo {field_name} no puede ser negativo.')

        monto_recibido = attrs.get('monto_recibido')
        if monto_recibido is not None and monto_recibido < 0:
            raise serializers.ValidationError({'monto_recibido': 'El monto recibido no puede ser negativo.'})

        cuota_numero = extract_cuota_numero_from_documento(documento)
        request = self.context.get('request')
        if prestamo is not None and request is not None and instance is None:
            prestamo_pk = getattr(prestamo, 'pk', None) or getattr(prestamo, 'id_prestamo', None)
            if prestamo_pk:
                prestamo = Prestamo.objects.select_related('id_cartera').get(pk=prestamo_pk)
            validar_cobro_por_cartera(request, prestamo)

        if prestamo is not None and cuota_numero is not None and instance is None:
            plan_rows = list(
                PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota')
            )
            pagos_existentes = list(self._pagos_existentes(prestamo))
            abonado_previo = abonado_por_cuota_desde_pagos(pagos_existentes)
            abonado_total = total_abonado_prestamo(pagos_existentes)
            self._validar_cuota_inicio_abierta(
                prestamo, cuota_numero, plan_rows, abonado_previo, abonado_total,
            )
        return attrs

    @staticmethod
    def _sync_prestamo_state(prestamo: Prestamo, pago: Pago) -> None:
        """Actualiza estado y dias de mora del prestamo en base al pago."""
        saldo = Decimal(pago.saldo)
        dias_mora = 0
        if pago.fecha_pago and prestamo.fecha_vencimiento and pago.fecha_pago > prestamo.fecha_vencimiento:
            dias_mora = (pago.fecha_pago - prestamo.fecha_vencimiento).days

        if saldo <= 0:
            prestamo.estado = 'pagado'
            prestamo.dias_mora = 0
        elif dias_mora > 0:
            prestamo.estado = 'mora'
            prestamo.dias_mora = max(dias_mora, prestamo.dias_mora)
        else:
            prestamo.estado = 'activo'
            prestamo.dias_mora = 0

        prestamo.save(update_fields=['estado', 'dias_mora'])

    @transaction.atomic
    def create(self, validated_data):
        monto_recibido = validated_data.pop('monto_recibido', None)
        monto_recibido_cliente = (
            round_money(Decimal(monto_recibido)) if monto_recibido is not None else None
        )
        cobrado_en = validated_data.pop('cobrado_en', None) or timezone.now()
        prestamo = validated_data.get('id_prestamo')
        documento = validated_data.get('documento')
        cuota_numero = extract_cuota_numero_from_documento(documento)

        if prestamo is not None:
            Prestamo.objects.select_for_update().get(pk=prestamo.pk)

        plan_rows = (
            list(PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota'))
            if prestamo is not None
            else []
        )
        abonado_previo = (
            abonado_por_cuota_desde_pagos(self._pagos_existentes(prestamo)) if prestamo else {}
        )

        # Cobros sin cargo por mora: siempre se registra en 0.
        validated_data['mora'] = Decimal('0.00')
        mora = Decimal('0.00')
        if monto_recibido is not None:
            monto_distribuir = round_money(Decimal(monto_recibido))
        else:
            monto_distribuir = round_money(
                Decimal(validated_data.get('capital', 0)) + Decimal(validated_data.get('interes', 0))
            )

        debe_distribuir = False
        if prestamo is not None and cuota_numero is not None and plan_rows and monto_distribuir > 0:
            fila_inicio = next((row for row in plan_rows if row.numero_cuota == cuota_numero), None)
            pendiente_inicio = (
                pendiente_cuota(fila_inicio, abonado_previo.get(cuota_numero, Decimal('0.00')))
                if fila_inicio
                else Decimal('0.00')
            )
            if monto_recibido is not None:
                debe_distribuir = True
            elif pendiente_inicio > 0 and monto_distribuir > pendiente_inicio:
                debe_distribuir = True

        if debe_distribuir:
            lineas = distribuir_monto_en_cuotas(
                plan_rows,
                cuota_numero,
                monto_distribuir,
                mora,
                abonado_previo,
            )
            if lineas:
                fecha_pago = validated_data['fecha_pago']

                def _linea_distribucion_resumen(linea: dict) -> dict:
                    total = round_money(linea['capital'] + linea['interes'] + linea['mora'])
                    item: dict = {
                        'capital': str(linea['capital']),
                        'interes': str(linea['interes']),
                        'mora': str(linea['mora']),
                        'total': str(total),
                    }
                    if linea.get('abono_capital'):
                        item['abono_capital'] = True
                        if linea.get('liquida_prestamo'):
                            item['liquida_prestamo'] = True
                    else:
                        item['cuota'] = linea['numero_cuota']
                    if linea.get('parcial'):
                        item['parcial'] = True
                    return item

                self.distribucion_resumen = [_linea_distribucion_resumen(linea) for linea in lineas]
                detalle_factura = [dict(item) for item in self.distribucion_resumen]
                capital_total = round_money(sum((linea['capital'] for linea in lineas), Decimal('0.00')))
                interes_total = round_money(sum((linea['interes'] for linea in lineas), Decimal('0.00')))
                mora_total = round_money(sum((linea['mora'] for linea in lineas), Decimal('0.00')))
                saldo_final = lineas[-1]['saldo']
                # El documento del pago único siempre referencia la cuota (no el abono a capital),
                # para que abonado_por_cuota_desde_pagos lo asocie correctamente.
                documento_principal = next(
                    (linea['documento'] for linea in lineas if not linea.get('abono_capital')),
                    lineas[0]['documento'],
                )
                pago_unico = Pago.objects.create(
                    id_prestamo=prestamo,
                    fecha_pago=fecha_pago,
                    cobrado_en=cobrado_en,
                    documento=documento_principal,
                    capital=capital_total,
                    interes=interes_total,
                    mora=mora_total,
                    saldo=saldo_final,
                    monto_recibido_cliente=monto_recibido_cliente,
                    detalle_distribucion=detalle_factura,
                )
                _asignar_factura_sar_al_pago(pago_unico)
                self._sync_prestamo_state(prestamo, pago_unico)
                return pago_unico

        if plan_rows and cuota_numero is not None:
            validated_data['saldo'] = saldo_pendiente_tras_abono(
                plan_rows,
                abonado_previo,
                cuota_numero,
                Decimal(validated_data.get('capital', 0)),
                Decimal(validated_data.get('interes', 0)),
                mora,
            )

        if monto_recibido_cliente is not None:
            validated_data['monto_recibido_cliente'] = monto_recibido_cliente

        validated_data['cobrado_en'] = cobrado_en

        pago = super().create(validated_data)
        _asignar_factura_sar_al_pago(pago)
        self.distribucion_resumen = None
        self._sync_prestamo_state(pago.id_prestamo, pago)
        return pago

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop('monto_recibido', None)
        validated_data.pop('cobrado_en', None)
        prestamo = validated_data.get('id_prestamo', instance.id_prestamo)
        documento = validated_data.get('documento', instance.documento)
        cuota_numero = extract_cuota_numero_from_documento(documento)
        if prestamo is not None and cuota_numero is not None:
            Prestamo.objects.select_for_update().get(pk=prestamo.pk)
            plan_rows = list(
                PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota')
            )
            abonado_previo = abonado_por_cuota_desde_pagos(
                self._pagos_existentes(prestamo, instance_pk=instance.pk)
            )
            self._validar_cuota_inicio_abierta(prestamo, cuota_numero, plan_rows, abonado_previo)
        pago = super().update(instance, validated_data)
        self.distribucion_resumen = None
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


class ConfiguracionFacturacionSerializer(serializers.ModelSerializer):
    """Configuracion fiscal SAR (singleton pk=1)."""

    rango_autorizado_texto = serializers.SerializerMethodField(read_only=True)
    numero_ejemplo = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ConfiguracionFacturacion
        fields = (
            'id',
            'razon_social',
            'nombre_comercial',
            'rtn',
            'direccion',
            'ciudad',
            'telefono',
            'correo',
            'cai',
            'fecha_limite_emision',
            'establecimiento',
            'punto_emision',
            'tipo_documento',
            'correlativo_desde',
            'correlativo_hasta',
            'correlativo_actual',
            'usar_numeracion_sar',
            'formato_ticket',
            'aplicar_isv',
            'porcentaje_isv',
            'leyenda_exento',
            'leyenda_pie',
            'actualizado_en',
            'rango_autorizado_texto',
            'numero_ejemplo',
        )
        read_only_fields = ('id', 'actualizado_en', 'rango_autorizado_texto', 'numero_ejemplo')

    def get_rango_autorizado_texto(self, obj: ConfiguracionFacturacion) -> str:
        return texto_rango_autorizado(obj)

    def get_numero_ejemplo(self, obj: ConfiguracionFacturacion) -> str:
        return formatear_numero_factura_sar(
            obj.establecimiento,
            obj.punto_emision,
            obj.tipo_documento,
            obj.correlativo_actual,
        )

    def validate(self, attrs):
        desde = attrs.get('correlativo_desde', getattr(self.instance, 'correlativo_desde', 1))
        hasta = attrs.get('correlativo_hasta', getattr(self.instance, 'correlativo_hasta', 1))
        actual = attrs.get('correlativo_actual', getattr(self.instance, 'correlativo_actual', 1))
        if hasta < desde:
            raise serializers.ValidationError(
                {'correlativo_hasta': 'El correlativo final debe ser mayor o igual al inicial.'},
            )
        if not (desde <= actual <= hasta):
            raise serializers.ValidationError(
                {'correlativo_actual': 'El correlativo actual debe estar dentro del rango autorizado.'},
            )
        for field_name in ('establecimiento', 'punto_emision'):
            value = str(attrs.get(field_name, getattr(self.instance, field_name, '001'))).strip()
            if not value.isdigit() or len(value) > 3:
                raise serializers.ValidationError(
                    {field_name: 'Use hasta 3 digitos numericos (ej. 001).'},
                )
        tipo = str(attrs.get('tipo_documento', getattr(self.instance, 'tipo_documento', '01'))).strip()
        if not tipo.isdigit() or len(tipo) > 2:
            raise serializers.ValidationError(
                {'tipo_documento': 'Use hasta 2 digitos numericos (01 = factura).'},
            )
        pct = attrs.get('porcentaje_isv', getattr(self.instance, 'porcentaje_isv', Decimal('15')))
        if pct is not None and pct < 0:
            raise serializers.ValidationError({'porcentaje_isv': 'El porcentaje de ISV no puede ser negativo.'})
        return attrs


def _asignar_factura_sar_al_pago(pago: Pago) -> None:
    try:
        asignar_numero_factura_sar(pago)
    except ErrorFacturacionSAR as exc:
        raise serializers.ValidationError({'detail': str(exc)}) from exc

