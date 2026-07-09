"""Índices para consultas frecuentes: historial de cobros, hoja móvil y reportes."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0035_pago_registrado_por'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='cliente',
            index=models.Index(fields=['nombre'], name='idx_cliente_nombre'),
        ),
        migrations.AddIndex(
            model_name='usuario',
            index=models.Index(fields=['rol'], name='idx_usuario_rol'),
        ),
        migrations.AddIndex(
            model_name='prestamo',
            index=models.Index(
                fields=['id_cartera', 'estado'],
                name='idx_prestamo_cartera_estado',
            ),
        ),
        migrations.AddIndex(
            model_name='prestamo',
            index=models.Index(
                fields=['id_cliente', 'estado'],
                name='idx_prestamo_cliente_estado',
            ),
        ),
        migrations.AddIndex(
            model_name='prestamo',
            index=models.Index(fields=['fecha_entrega'], name='idx_prestamo_fecha_entrega'),
        ),
        migrations.AddIndex(
            model_name='pago',
            index=models.Index(
                fields=['anulado', 'fecha_pago'],
                name='idx_pago_anulado_fecha',
            ),
        ),
        migrations.AddIndex(
            model_name='pago',
            index=models.Index(
                fields=['id_prestamo', 'anulado', 'fecha_pago'],
                name='idx_pago_prestamo_vigente',
            ),
        ),
    ]
