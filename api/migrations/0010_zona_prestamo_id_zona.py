"""Catálogo zonas (Comayagua, Siguatepeque, La Paz) y FK en préstamos."""

import django.db.models.deletion
from django.db import migrations, models


def seed_zonas(apps, schema_editor):
    Zona = apps.get_model('api', 'Zona')
    for codigo, nombre in (
        ('comayagua', 'Comayagua'),
        ('siguatepeque', 'Siguatepeque'),
        ('la-paz', 'La Paz'),
    ):
        Zona.objects.get_or_create(codigo=codigo, defaults={'nombre': nombre})


def reverse_seed(apps, schema_editor):
    Zona = apps.get_model('api', 'Zona')
    Zona.objects.filter(codigo__in=('comayagua', 'siguatepeque', 'la-paz')).delete()


class Migration(migrations.Migration):
    """En MySQL/MariaDB conviene DDL fuera de transacción única (commits implícitos)."""

    atomic = False

    dependencies = [
        ('api', '0009_contratoprestamo'),
    ]

    operations = [
        migrations.CreateModel(
            name='Zona',
            fields=[
                ('id_zona', models.AutoField(primary_key=True, serialize=False)),
                ('codigo', models.SlugField(max_length=40, unique=True)),
                ('nombre', models.CharField(max_length=80)),
            ],
            options={
                'db_table': 'zonas',
                'ordering': ['nombre'],
            },
        ),
        migrations.RunPython(seed_zonas, reverse_seed, atomic=False),
        migrations.AddField(
            model_name='prestamo',
            name='id_zona',
            field=models.ForeignKey(
                blank=True,
                db_column='id_zona',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prestamos',
                to='api.zona',
            ),
        ),
    ]
