from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0032_configuracion_facturacion_sar'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='rtn',
            field=models.CharField(
                blank=True,
                help_text='RTN del cliente (persona jurídica o cuando aplica facturación).',
                max_length=20,
                null=True,
            ),
        ),
    ]
