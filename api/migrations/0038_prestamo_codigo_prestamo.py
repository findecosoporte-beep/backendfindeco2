from django.db import migrations, models


def _backfill_codigo_prestamo(apps, schema_editor):
    Prestamo = apps.get_model('api', 'Prestamo')
    for prestamo in Prestamo.objects.all().only('id_prestamo', 'numero_prestamo'):
        texto = (prestamo.numero_prestamo or '').strip()
        prestamo.codigo_prestamo = texto or str(prestamo.id_prestamo).zfill(3)
        prestamo.save(update_fields=['codigo_prestamo'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_usuario_telefono'),
    ]

    operations = [
        migrations.AddField(
            model_name='prestamo',
            name='codigo_prestamo',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.RunPython(_backfill_codigo_prestamo, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='prestamo',
            name='codigo_prestamo',
            field=models.CharField(max_length=20, unique=True),
        ),
    ]
