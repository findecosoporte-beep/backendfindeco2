from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0029_pago_id_pago_factura'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='creado_en',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='cobrado_en',
            field=models.DateTimeField(
                blank=True,
                help_text='Fecha y hora en que se registró el cobro (factura y auditoría).',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='prestamo',
            name='creado_en',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
    ]
