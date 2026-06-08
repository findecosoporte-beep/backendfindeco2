from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_gestion_cobranza'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrestamoCuota',
            fields=[
                ('id_cuota', models.AutoField(primary_key=True, serialize=False)),
                ('numero_cuota', models.IntegerField()),
                ('fecha_programada', models.DateField()),
                ('capital_programado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('interes_programado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('servicios_programado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('otros_programado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_programado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('saldo_capital_programado', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    'estado',
                    models.CharField(
                        choices=[
                            ('pendiente', 'pendiente'),
                            ('pagada', 'pagada'),
                            ('vencida', 'vencida'),
                            ('parcial', 'parcial'),
                        ],
                        default='pendiente',
                        max_length=20,
                    ),
                ),
                ('fecha_pago_real', models.DateField(blank=True, null=True)),
                (
                    'id_prestamo',
                    models.ForeignKey(
                        db_column='id_prestamo',
                        on_delete=django.db.models.deletion.CASCADE,
                        to='api.prestamo',
                    ),
                ),
            ],
            options={
                'db_table': 'prestamo_cuotas',
                'ordering': ['id_prestamo', 'numero_cuota'],
            },
        ),
        migrations.AddConstraint(
            model_name='prestamocuota',
            constraint=models.UniqueConstraint(
                fields=('id_prestamo', 'numero_cuota'),
                name='uq_prestamo_cuota_numero',
            ),
        ),
    ]
