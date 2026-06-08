from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_clientedocumento_sha256'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContratoPrestamo',
            fields=[
                ('id_contrato', models.AutoField(primary_key=True, serialize=False)),
                ('titulo', models.CharField(max_length=180)),
                ('contenido', models.TextField()),
                ('actor', models.CharField(default='Operador', max_length=100)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                (
                    'id_cliente',
                    models.ForeignKey(
                        db_column='id_cliente',
                        on_delete=django.db.models.deletion.CASCADE,
                        to='api.cliente',
                    ),
                ),
                (
                    'id_documento',
                    models.ForeignKey(
                        blank=True,
                        db_column='id_documento',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to='api.clientedocumento',
                    ),
                ),
                (
                    'id_prestamo',
                    models.ForeignKey(
                        blank=True,
                        db_column='id_prestamo',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to='api.prestamo',
                    ),
                ),
            ],
            options={
                'db_table': 'contratos_prestamo',
                'ordering': ['-creado_en', '-id_contrato'],
            },
        ),
    ]
