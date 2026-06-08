"""Campos estructurados de persona de referencia (parentesco y teléfono)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_cartera_dia_cobro_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='referencia_parentesco',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='referencia_telefono',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
