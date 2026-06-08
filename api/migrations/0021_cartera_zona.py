"""Vincula carteras generadas automáticamente desde zonas (OneToOne)."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_zona_dia_semana'),
    ]

    operations = [
        migrations.AddField(
            model_name='cartera',
            name='zona',
            field=models.OneToOneField(
                blank=True,
                help_text='Si está ligada, la cartera se crea o actualiza al guardar la zona (nombre y día de cobro).',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='cartera_sincronizada',
                to='api.zona',
            ),
        ),
    ]
