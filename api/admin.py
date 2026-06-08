"""Registro de modelos para el panel de administracion de Django."""

from django.contrib import admin

from .models import (
    Cartera,
    Cliente,
    HistorialPrestamo,
    Pago,
    Prestamo,
    PrestamoCuota,
    Servicio,
    Usuario,
    Zona,
)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    """Configuracion admin de clientes."""

    list_display = ('id_cliente', 'nombre', 'dni', 'dia_cobro_semanal', 'telefono')
    search_fields = ('nombre', 'dni', 'telefono')


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    """Catálogo de zonas."""

    search_fields = ('nombre', 'codigo')
    list_display = ('id_zona', 'codigo', 'nombre', 'dia_semana_etiqueta')

    @admin.display(description='Día semana')
    def dia_semana_etiqueta(self, obj):
        return obj.get_dia_semana_display() if obj.dia_semana else '—'


@admin.register(Cartera)
class CarteraAdmin(admin.ModelAdmin):
    """Carteras operativas."""

    search_fields = ('nombre', 'dia_cobro')
    list_display = ('id_cartera', 'nombre', 'dia_cobro_etiqueta', 'zona_etiqueta')

    @admin.display(description='Día de cobro')
    def dia_cobro_etiqueta(self, obj):
        return obj.get_dia_cobro_display()

    @admin.display(description='Zona vinculada')
    def zona_etiqueta(self, obj):
        return obj.zona.nombre if obj.zona_id else '—'


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    """Configuracion admin de usuarios."""

    list_display = ('id_usuario', 'nombre', 'rol', 'correo')
    list_filter = ('rol',)
    search_fields = ('nombre', 'correo')


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    """Configuracion admin de prestamos."""

    list_display = ('id_prestamo', 'numero_prestamo', 'id_cliente', 'estado', 'monto', 'fecha_vencimiento')
    list_filter = ('estado', 'forma_pago', 'forma_desembolso')
    search_fields = ('numero_prestamo', 'id_cliente__nombre')


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    """Configuracion admin de pagos."""

    list_display = ('id_pago', 'id_prestamo', 'fecha_pago', 'capital', 'interes', 'saldo')
    list_filter = ('fecha_pago',)
    search_fields = ('documento', 'id_prestamo__numero_prestamo')


@admin.register(PrestamoCuota)
class PrestamoCuotaAdmin(admin.ModelAdmin):
    """Configuracion admin de cuotas planificadas de prestamo."""

    list_display = (
        'id_cuota',
        'id_prestamo',
        'numero_cuota',
        'fecha_programada',
        'total_programado',
        'estado',
    )
    list_filter = ('estado', 'fecha_programada')
    search_fields = ('id_prestamo__numero_prestamo',)


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    """Configuracion admin de servicios."""

    list_display = ('id_servicio', 'id_prestamo', 'codigo_servicio', 'nombre_servicio', 'porcentaje')
    list_filter = ('codigo_servicio',)
    search_fields = ('nombre_servicio', 'id_prestamo__numero_prestamo')


@admin.register(HistorialPrestamo)
class HistorialPrestamoAdmin(admin.ModelAdmin):
    """Configuracion admin de historico de prestamos."""

    list_display = ('id_historial', 'id_cliente', 'numero_prestamo', 'producto', 'monto', 'saldo')
    search_fields = ('numero_prestamo', 'id_cliente__nombre', 'producto')
