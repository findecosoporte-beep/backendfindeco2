"""Restringe dia_cobro de Cartera a días de la semana (choices)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_cartera'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cartera',
            name='dia_cobro',
            field=models.CharField(
                choices=[
                    ('lunes', 'Lunes'),
                    ('martes', 'Martes'),
                    ('miercoles', 'Miércoles'),
                    ('jueves', 'Jueves'),
                    ('viernes', 'Viernes'),
                    ('sabado', 'Sábado'),
                    ('domingo', 'Domingo'),
                ],
                max_length=16,
            ),
        ),
    ]
