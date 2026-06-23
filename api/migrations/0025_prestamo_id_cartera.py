"""Vincula préstamos con cartera operativa."""

import django.db.models.deletion
from django.db import migrations, models


def backfill_prestamo_cartera_desde_zona(apps, schema_editor):
    Prestamo = apps.get_model('api', 'Prestamo')
    Cartera = apps.get_model('api', 'Cartera')
    for prestamo in Prestamo.objects.filter(id_zona_id__isnull=False, id_cartera_id__isnull=True):
        cartera = Cartera.objects.filter(zona_id=prestamo.id_zona_id).first()
        if cartera:
            prestamo.id_cartera_id = cartera.id_cartera
            prestamo.save(update_fields=['id_cartera_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_cliente_dia_cobro_semanal'),
    ]

    operations = [
        migrations.AddField(
            model_name='prestamo',
            name='id_cartera',
            field=models.ForeignKey(
                blank=True,
                db_column='id_cartera',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prestamos',
                to='api.cartera',
            ),
        ),
        migrations.RunPython(backfill_prestamo_cartera_desde_zona, migrations.RunPython.noop),
    ]
