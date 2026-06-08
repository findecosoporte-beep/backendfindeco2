# Generated manually for dia_cobro_semanal on Cliente

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_revert_tasa_nominal_mensual'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='dia_cobro_semanal',
            field=models.CharField(
                blank=True,
                choices=[
                    ('lunes', 'Lunes'),
                    ('martes', 'Martes'),
                    ('miercoles', 'Miércoles'),
                    ('jueves', 'Jueves'),
                    ('viernes', 'Viernes'),
                    ('sabado', 'Sábado'),
                    ('domingo', 'Domingo'),
                ],
                help_text='Día de la semana preferido para visita o cobro al cliente.',
                max_length=16,
                null=True,
            ),
        ),
    ]
