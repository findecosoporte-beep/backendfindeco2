from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_usuario_cartera_cobrador'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='monto_recibido_cliente',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Efectivo entregado por el cliente en este cobro (factura).',
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='pago',
            name='detalle_distribucion',
            field=models.JSONField(
                blank=True,
                help_text='Desglose por cuota cuando el cobro se reparte en varias líneas.',
                null=True,
            ),
        ),
    ]
