"""Agrega teléfono al perfil operativo de usuario (cobradores)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_indices_rendimiento'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='telefono',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
