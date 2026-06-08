"""Tasa de préstamo como TIN anual (%); migra valores guardados como mensual nominal × 12."""

from django.db import migrations, models
from django.db.models import F


def prestamos_tasas_mensual_a_anual(apps, schema_editor):
    Prestamo = apps.get_model('api', 'Prestamo')
    Prestamo.objects.update(tasa_interes=F('tasa_interes') * 12)

    HistorialPrestamo = apps.get_model('api', 'HistorialPrestamo')
    HistorialPrestamo.objects.filter(tasa__isnull=False).update(tasa=F('tasa') * 12)


def prestamos_tasas_anual_a_mensual(apps, schema_editor):
    Prestamo = apps.get_model('api', 'Prestamo')
    Prestamo.objects.update(tasa_interes=F('tasa_interes') / 12)

    HistorialPrestamo = apps.get_model('api', 'HistorialPrestamo')
    HistorialPrestamo.objects.filter(tasa__isnull=False).update(tasa=F('tasa') / 12)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_cartera_zona'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prestamo',
            name='tasa_interes',
            field=models.DecimalField(
                decimal_places=2,
                help_text='Tasa de interés nominal anual (TIN) en %. Se usa TIN÷12 como tasa mensual nominal para el plan de cuotas.',
                max_digits=7,
            ),
        ),
        migrations.AlterField(
            model_name='historialprestamo',
            name='tasa',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.RunPython(prestamos_tasas_mensual_a_anual, prestamos_tasas_anual_a_mensual),
    ]
