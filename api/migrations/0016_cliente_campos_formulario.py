"""Cliente: DNI, teléfono único, direcciones, referencia, actividad económica."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_cliente_ocupacion_sin_expediente'),
    ]

    operations = [
        migrations.RenameField(model_name='cliente', old_name='identidad', new_name='dni'),
        migrations.RenameField(model_name='cliente', old_name='telefono_celular', new_name='telefono'),
        migrations.RenameField(model_name='cliente', old_name='direccion', new_name='direccion_residencia'),
        migrations.RenameField(model_name='cliente', old_name='ocupacion', new_name='actividad_economica'),
        migrations.AddField(
            model_name='cliente',
            name='direccion_negocio',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='referencia',
            field=models.TextField(blank=True, null=True),
        ),
    ]
