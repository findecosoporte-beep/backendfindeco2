# Generated manually for anulación de cobros

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_fechas_evento_cobro_cliente_prestamo'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='anulado',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='Cobro anulado; no cuenta en saldos ni reportes.',
            ),
        ),
        migrations.AddField(
            model_name='pago',
            name='anulado_en',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='anulado_por',
            field=models.ForeignKey(
                blank=True,
                db_column='anulado_por',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pagos_anulados',
                to='api.usuario',
            ),
        ),
        migrations.AddField(
            model_name='pago',
            name='motivo_anulacion',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
