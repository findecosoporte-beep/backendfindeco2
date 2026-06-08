"""Asegura `prestamos.estado` como VARCHAR suficientemente largo (MySQL ENUM heredados rompen `pendiente_aprobacion`)."""

from django.db import migrations, models


def prestamos_estado_a_varchar_mysql(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != 'mysql':
        return
    with conn.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE `prestamos` MODIFY COLUMN `estado` VARCHAR(32) NOT NULL DEFAULT 'pendiente_aprobacion'"
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('api', '0010_zona_prestamo_id_zona'),
    ]

    operations = [
        migrations.RunPython(prestamos_estado_a_varchar_mysql, noop_reverse, atomic=False),
        migrations.AlterField(
            model_name='prestamo',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pendiente_aprobacion', 'pendiente_aprobacion'),
                    ('activo', 'activo'),
                    ('pagado', 'pagado'),
                    ('mora', 'mora'),
                    ('cancelado', 'cancelado'),
                ],
                default='pendiente_aprobacion',
                max_length=32,
            ),
        ),
    ]
