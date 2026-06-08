"""Cliente: quita teléfonos casa/negocio y expediente; añade ocupacion."""

from django.db import migrations, models


def copy_expediente_a_ocupacion(apps, schema_editor):
    Cliente = apps.get_model('api', 'Cliente')
    for row in Cliente.objects.all().iterator():
        notas = (getattr(row, 'notas_expediente', None) or '').strip()
        estado = (getattr(row, 'expediente_estado', None) or '').strip()
        perfil = (getattr(row, 'expediente_tipo_perfil', None) or '').strip()
        producto = (getattr(row, 'expediente_producto', None) or '').strip()
        chunks = []
        if estado and estado != 'borrador':
            chunks.append(f'Estado expediente (hist.): {estado}')
        if perfil:
            chunks.append(f'Perfil (hist.): {perfil}')
        if producto:
            chunks.append(f'Producto (hist.): {producto}')
        if notas:
            chunks.append(notas)
        merged = '\n'.join(chunks).strip()
        if merged:
            row.ocupacion = merged
            row.save(update_fields=['ocupacion'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_remove_gestion_and_ruta_cobranza'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='ocupacion',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.RunPython(copy_expediente_a_ocupacion, noop_reverse),
        migrations.RemoveField(model_name='cliente', name='telefono_casa'),
        migrations.RemoveField(model_name='cliente', name='telefono_negocio'),
        migrations.RemoveField(model_name='cliente', name='expediente_estado'),
        migrations.RemoveField(model_name='cliente', name='notas_expediente'),
        migrations.RemoveField(model_name='cliente', name='expediente_tipo_perfil'),
        migrations.RemoveField(model_name='cliente', name='expediente_producto'),
        migrations.RemoveField(model_name='cliente', name='expediente_completado_en'),
    ]
