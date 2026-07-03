from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_pago_monto_recibido_cliente'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='id_pago_factura',
            field=models.ForeignKey(
                blank=True,
                db_column='id_pago_factura',
                help_text='Pago maestro cuya factura consolida este abono (cobros repartidos).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pagos_mismo_cobro',
                to='api.pago',
            ),
        ),
    ]
