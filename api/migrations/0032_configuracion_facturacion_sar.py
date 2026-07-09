# Generated manually for configuracion SAR

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0031_pago_anulacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionFacturacion',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('razon_social', models.CharField(blank=True, default='', max_length=200)),
                ('nombre_comercial', models.CharField(blank=True, default='', max_length=200)),
                ('rtn', models.CharField(blank=True, default='', help_text='RTN del emisor', max_length=20)),
                ('direccion', models.CharField(blank=True, default='', max_length=300)),
                ('ciudad', models.CharField(blank=True, default='', max_length=100)),
                ('telefono', models.CharField(blank=True, default='', max_length=50)),
                ('correo', models.EmailField(blank=True, default='', max_length=254)),
                ('cai', models.CharField(blank=True, default='', help_text='Codigo de Autorizacion de Impresion (CAI) otorgado por SAR', max_length=40)),
                ('fecha_limite_emision', models.DateField(blank=True, help_text='Fecha limite de emision autorizada para el CAI', null=True)),
                ('establecimiento', models.CharField(default='001', max_length=3)),
                ('punto_emision', models.CharField(default='001', max_length=3)),
                ('tipo_documento', models.CharField(default='01', help_text='01 = Factura, 06 = Nota de credito, etc.', max_length=2)),
                ('correlativo_desde', models.PositiveIntegerField(default=1)),
                ('correlativo_hasta', models.PositiveIntegerField(default=99999999)),
                ('correlativo_actual', models.PositiveIntegerField(default=1, help_text='Proximo correlativo a asignar en un cobro')),
                ('usar_numeracion_sar', models.BooleanField(default=False, help_text='Si esta activo, cada cobro recibe numero SAR y valida CAI/rango.')),
                ('formato_ticket', models.CharField(choices=[('58', '58 mm'), ('80', '80 mm')], default='58', max_length=2)),
                ('aplicar_isv', models.BooleanField(default=False)),
                ('porcentaje_isv', models.DecimalField(decimal_places=2, default=15, max_digits=5)),
                ('leyenda_exento', models.CharField(blank=True, default='Operacion exenta / no sujeta a ISV', max_length=200)),
                ('leyenda_pie', models.CharField(blank=True, default='Gracias por su preferencia', max_length=300)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuracion de facturacion',
                'verbose_name_plural': 'Configuracion de facturacion',
                'db_table': 'configuracion_facturacion',
            },
        ),
        migrations.AddField(
            model_name='pago',
            name='numero_factura',
            field=models.CharField(blank=True, db_index=True, help_text='Numero correlativo SAR (XXX-XXX-XX-XXXXXXXX) asignado al cobro.', max_length=30, null=True),
        ),
    ]
