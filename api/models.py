"""Modelos de dominio para el sistema de prestamos."""

from django.db import models

# Día de semana (misma convención que `Zona.dia_semana` y `Cartera.dia_cobro`).
DIA_SEMANA_COBRANZA_CHOICES = (
    ('lunes', 'Lunes'),
    ('martes', 'Martes'),
    ('miercoles', 'Miércoles'),
    ('jueves', 'Jueves'),
    ('viernes', 'Viernes'),
    ('sabado', 'Sábado'),
    ('domingo', 'Domingo'),
)


class Cliente(models.Model):
    """Entidad de clientes."""

    objects = models.Manager()

    id_cliente = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    dni = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    direccion_residencia = models.CharField(max_length=200, null=True, blank=True)
    direccion_negocio = models.CharField(max_length=200, null=True, blank=True)
    referencia = models.TextField(null=True, blank=True)
    referencia_parentesco = models.CharField(max_length=80, null=True, blank=True)
    referencia_telefono = models.CharField(max_length=20, null=True, blank=True)
    actividad_economica = models.TextField(null=True, blank=True)
    dia_cobro_semanal = models.CharField(
        max_length=16,
        choices=DIA_SEMANA_COBRANZA_CHOICES,
        null=True,
        blank=True,
        help_text='Día de la semana preferido para visita o cobro al cliente.',
    )

    class Meta:
        """Mapeo ORM: tabla `clientes` y orden por id."""

        db_table = 'clientes'
        ordering = ['id_cliente']

    def __str__(self) -> str:
        return f'{self.id_cliente} - {self.nombre}'


class Usuario(models.Model):
    """Entidad de usuarios operativos."""

    objects = models.Manager()

    ROL_CHOICES = (
        ('administrador', 'administrador'),
        ('asesor', 'asesor'),
        ('supervisor', 'supervisor'),
        ('cobrador', 'cobrador'),
        (
            'cobranza_adm_jud',
            'Cobranza administrativa / judicial (segun mora)',
        ),
    )

    id_usuario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    rol = models.CharField(max_length=40, choices=ROL_CHOICES)
    correo = models.EmailField(max_length=100, unique=True, null=True, blank=True)
    clave = models.CharField(
        max_length=255,
        help_text='DEPRECADO: no usar para autenticación. El acceso es vía Django User + JWT.',
    )

    class Meta:
        """Mapeo ORM: tabla `usuarios` y orden por id."""

        db_table = 'usuarios'
        ordering = ['id_usuario']

    def __str__(self) -> str:
        return f'{self.id_usuario} - {self.nombre}'


class Zona(models.Model):
    """Territorios / zonas operativas (catálogo en BD para préstamos y cobranza)."""

    objects = models.Manager()

    DIA_SEMANA_CHOICES = DIA_SEMANA_COBRANZA_CHOICES

    id_zona = models.AutoField(primary_key=True)
    codigo = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=80)
    dia_semana = models.CharField(
        max_length=16,
        choices=DIA_SEMANA_CHOICES,
        null=True,
        blank=True,
        help_text='Día de la semana asignado a la ruta / cobro en esa zona.',
    )

    class Meta:
        """Mapeo ORM: tabla `zonas` y orden por nombre."""

        db_table = 'zonas'
        ordering = ['nombre']

    def __str__(self) -> str:
        return str(self.nombre)


class Cartera(models.Model):
    """Cartera operativa con día de cobro asignado."""

    objects = models.Manager()

    DIA_COBRO_CHOICES = (
        ('lunes', 'Lunes'),
        ('martes', 'Martes'),
        ('miercoles', 'Miércoles'),
        ('jueves', 'Jueves'),
        ('viernes', 'Viernes'),
        ('sabado', 'Sábado'),
        ('domingo', 'Domingo'),
    )

    id_cartera = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=120)
    dia_cobro = models.CharField(max_length=16, choices=DIA_COBRO_CHOICES)
    zona = models.OneToOneField(
        'Zona',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cartera_sincronizada',
        help_text='Si está ligada, la cartera se crea o actualiza al guardar la zona (nombre y día de cobro).',
    )

    class Meta:
        """Mapeo ORM: tabla `carteras` y orden por nombre."""

        db_table = 'carteras'
        ordering = ['nombre']

    def __str__(self) -> str:
        return f'{self.nombre} ({self.dia_cobro})'


class UsuarioCartera(models.Model):
    """Asignación de cobrador a cartera operativa (una cartera, un cobrador)."""

    objects = models.Manager()

    id_usuario_cartera = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        db_column='id_usuario',
        related_name='carteras_asignadas',
    )
    id_cartera = models.ForeignKey(
        Cartera,
        on_delete=models.CASCADE,
        db_column='id_cartera',
        related_name='cobradores_asignados',
    )

    class Meta:
        db_table = 'usuario_carteras'
        ordering = ['id_cartera_id']
        constraints = [
            models.UniqueConstraint(fields=['id_cartera'], name='uniq_cartera_un_cobrador'),
        ]

    def __str__(self) -> str:
        return f'Cobrador {self.id_usuario_id} → Cartera {self.id_cartera_id}'


class Prestamo(models.Model):
    """Entidad principal de prestamos."""

    objects = models.Manager()

    ESTADO_CHOICES = (
        ('pendiente_aprobacion', 'pendiente_aprobacion'),
        ('activo', 'activo'),
        ('pagado', 'pagado'),
        ('mora', 'mora'),
        ('cancelado', 'cancelado'),
    )
    FORMA_PAGO_CHOICES = (
        ('semanal', 'semanal'),
        ('mensual', 'mensual'),
        ('quincenal', 'quincenal'),
    )
    FORMA_DESEMBOLSO_CHOICES = (
        ('efectivo', 'efectivo'),
        ('transferencia', 'transferencia'),
        ('cheque', 'cheque'),
    )

    id_prestamo = models.AutoField(primary_key=True)
    numero_prestamo = models.CharField(max_length=20, unique=True)
    sucursal = models.CharField(max_length=100, null=True, blank=True)
    id_zona = models.ForeignKey(
        Zona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_zona',
        related_name='prestamos',
    )
    id_cartera = models.ForeignKey(
        Cartera,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_cartera',
        related_name='prestamos',
    )
    ciclos = models.IntegerField(default=0)
    supervisor = models.CharField(max_length=100, null=True, blank=True)
    asesor = models.CharField(max_length=100, null=True, blank=True)
    dias_mora = models.IntegerField(default=0)
    categoria_crediticia = models.CharField(max_length=50, null=True, blank=True)
    id_cliente = models.ForeignKey(Cliente, on_delete=models.RESTRICT, db_column='id_cliente')
    id_usuario = models.ForeignKey(Usuario, on_delete=models.RESTRICT, db_column='id_usuario')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    plazo = models.IntegerField()
    tasa_interes = models.DecimalField(max_digits=5, decimal_places=2)
    tipo_garantia = models.CharField(max_length=50, null=True, blank=True)
    estado = models.CharField(max_length=32, choices=ESTADO_CHOICES, default='pendiente_aprobacion')
    forma_pago = models.CharField(max_length=20, choices=FORMA_PAGO_CHOICES)
    forma_desembolso = models.CharField(max_length=20, choices=FORMA_DESEMBOLSO_CHOICES)
    comision = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    producto = models.CharField(max_length=50, null=True, blank=True)
    categoria = models.CharField(max_length=50, null=True, blank=True)
    fecha_entrega = models.DateField()
    fecha_vencimiento = models.DateField()

    class Meta:
        """Mapeo ORM: tabla `prestamos` y orden descendente por id."""

        db_table = 'prestamos'
        ordering = ['-id_prestamo']

    def __str__(self) -> str:
        return str(self.numero_prestamo or f'Prestamo #{self.id_prestamo}')


class PrestamoCuota(models.Model):
    """Plan de pagos persistido por cuota para cada prestamo."""

    objects = models.Manager()

    ESTADO_CHOICES = (
        ('pendiente', 'pendiente'),
        ('pagada', 'pagada'),
        ('vencida', 'vencida'),
        ('parcial', 'parcial'),
    )

    id_cuota = models.AutoField(primary_key=True)
    id_prestamo = models.ForeignKey(Prestamo, on_delete=models.CASCADE, db_column='id_prestamo')
    numero_cuota = models.IntegerField()
    fecha_programada = models.DateField()
    capital_programado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    interes_programado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    servicios_programado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    otros_programado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_programado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_capital_programado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_pago_real = models.DateField(null=True, blank=True)

    class Meta:
        """Mapeo ORM: tabla `prestamo_cuotas`, orden y unicidad por préstamo."""

        db_table = 'prestamo_cuotas'
        ordering = ['id_prestamo', 'numero_cuota']
        constraints = [
            models.UniqueConstraint(
                fields=['id_prestamo', 'numero_cuota'],
                name='uq_prestamo_cuota_numero',
            ),
        ]

    def __str__(self) -> str:
        prestamo = self.id_prestamo
        prestamo_id = prestamo.id_prestamo if prestamo is not None else '?'
        return f'Cuota #{self.numero_cuota} - Prestamo {prestamo_id}'


class Pago(models.Model):
    """Entidad de pagos realizados por prestamo."""

    objects = models.Manager()

    id_pago = models.AutoField(primary_key=True)
    id_prestamo = models.ForeignKey(Prestamo, on_delete=models.RESTRICT, db_column='id_prestamo')
    fecha_pago = models.DateField()
    documento = models.CharField(max_length=50, null=True, blank=True)
    capital = models.DecimalField(max_digits=12, decimal_places=2)
    interes = models.DecimalField(max_digits=12, decimal_places=2)
    mora = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        """Mapeo ORM: tabla `pagos` y orden por fecha e id."""

        db_table = 'pagos'
        ordering = ['-fecha_pago', '-id_pago']

    def __str__(self) -> str:
        return f'Pago #{self.id_pago}'


class Servicio(models.Model):
    """Servicios o cargos asociados a un prestamo."""

    objects = models.Manager()

    id_servicio = models.AutoField(primary_key=True)
    id_prestamo = models.ForeignKey(Prestamo, on_delete=models.RESTRICT, db_column='id_prestamo')
    codigo_servicio = models.IntegerField()
    nombre_servicio = models.CharField(max_length=100)
    inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    abono = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        """Mapeo ORM: tabla `servicios` y orden por id."""

        db_table = 'servicios'
        ordering = ['id_servicio']

    def __str__(self) -> str:
        return str(self.nombre_servicio or f'Servicio #{self.id_servicio}')


class HistorialPrestamo(models.Model):
    """Entidad historica de prestamos por cliente."""

    objects = models.Manager()

    id_historial = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey(Cliente, on_delete=models.RESTRICT, db_column='id_cliente')
    numero_prestamo = models.CharField(max_length=20)
    producto = models.CharField(max_length=50, null=True, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    interes = models.DecimalField(max_digits=12, decimal_places=2)
    plazo = models.IntegerField(null=True, blank=True)
    tasa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saldo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        """Mapeo ORM: tabla `historial_prestamos` y orden descendente por id."""

        db_table = 'historial_prestamos'
        ordering = ['-id_historial']

    def __str__(self) -> str:
        return f'Historial #{self.id_historial}'


class ClienteDocumento(models.Model):
    """Documento cargado para el expediente de un cliente."""

    objects = models.Manager()

    id_documento = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, db_column='id_cliente')
    archivo = models.FileField(upload_to='clientes/documentos/%Y/%m/')
    nombre_archivo = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, null=True, blank=True)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    actor = models.CharField(max_length=100, default='Operador')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Mapeo ORM: tabla `cliente_documentos` y orden por fecha de alta."""

        db_table = 'cliente_documentos'
        ordering = ['-creado_en', '-id_documento']

    def __str__(self) -> str:
        return str(self.nombre_archivo or f'Documento #{self.id_documento}')


class ContratoPrestamo(models.Model):
    """Plantilla/versión textual de contrato por cliente y préstamo."""

    objects = models.Manager()

    id_contrato = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, db_column='id_cliente')
    id_prestamo = models.ForeignKey(
        Prestamo,
        on_delete=models.SET_NULL,
        db_column='id_prestamo',
        null=True,
        blank=True,
    )
    id_documento = models.ForeignKey(
        ClienteDocumento,
        on_delete=models.SET_NULL,
        db_column='id_documento',
        null=True,
        blank=True,
    )
    titulo = models.CharField(max_length=180)
    contenido = models.TextField()
    actor = models.CharField(max_length=100, default='Operador')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        """Mapeo ORM: tabla `contratos_prestamo` y orden por fecha de alta."""

        db_table = 'contratos_prestamo'
        ordering = ['-creado_en', '-id_contrato']

    def __str__(self) -> str:
        return str(self.titulo or f'Contrato #{self.id_contrato}')


class HojaCobroImpresion(models.Model):
    """Bitácora de impresiones de hoja de cobros con correlativo persistente."""

    objects = models.Manager()

    id_impresion = models.AutoField(primary_key=True)
    numero_impresion = models.PositiveIntegerField(unique=True)
    generado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_usuario',
        related_name='impresiones_hoja_cobro',
    )
    total_registros = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Mapeo ORM: tabla `hoja_cobro_impresiones` y orden por fecha de alta."""

        db_table = 'hoja_cobro_impresiones'
        ordering = ['-creado_en', '-id_impresion']

    def __str__(self) -> str:
        return f'Impresión hoja cobro #{self.numero_impresion}'
