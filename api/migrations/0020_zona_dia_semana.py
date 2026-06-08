"""Añade día de semana opcional a zonas (ruta / cobro)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_cliente_referencia_contacto'),
    ]

    operations = [
        migrations.AddField(
            model_name='zona',
            name='dia_semana',
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
                help_text='Día de la semana asignado a la ruta / cobro en esa zona.',
                max_length=16,
                null=True,
            ),
        ),
    ]
