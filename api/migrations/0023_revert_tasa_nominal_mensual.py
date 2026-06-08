"""Revierte 0022: tasa otra vez como nominal mensual (%) y campos a 5 dígitos."""

from django.db import migrations, models
from django.db.models import F


def revertir_tin_anual_a_mensual(apps, schema_editor):
    Prestamo = apps.get_model('api', 'Prestamo')
    Prestamo.objects.update(tasa_interes=F('tasa_interes') / 12)

    HistorialPrestamo = apps.get_model('api', 'HistorialPrestamo')
    HistorialPrestamo.objects.filter(tasa__isnull=False).update(tasa=F('tasa') / 12)


def volver_a_tin_anual_en_bd(apps, schema_editor):
    Prestamo = apps.get_model('api', 'Prestamo')
    Prestamo.objects.update(tasa_interes=F('tasa_interes') * 12)

    HistorialPrestamo = apps.get_model('api', 'HistorialPrestamo')
    HistorialPrestamo.objects.filter(tasa__isnull=False).update(tasa=F('tasa') * 12)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_prestamo_tasa_tin_anual'),
    ]

    operations = [
        migrations.RunPython(revertir_tin_anual_a_mensual, volver_a_tin_anual_en_bd),
        migrations.AlterField(
            model_name='prestamo',
            name='tasa_interes',
            field=models.DecimalField(decimal_places=2, max_digits=5),
        ),
        migrations.AlterField(
            model_name='historialprestamo',
            name='tasa',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
    ]
