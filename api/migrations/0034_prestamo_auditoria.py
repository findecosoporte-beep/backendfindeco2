from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0033_cliente_rtn'),
    ]

    operations = [
        migrations.AddField(
            model_name='prestamo',
            name='actualizado_en',
            field=models.DateTimeField(auto_now=True, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='prestamo',
            name='creado_por',
            field=models.ForeignKey(
                blank=True,
                db_column='creado_por',
                help_text='Usuario operativo que registró el préstamo en el sistema.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prestamos_creados',
                to='api.usuario',
            ),
        ),
        migrations.AddField(
            model_name='prestamo',
            name='modificado_por',
            field=models.ForeignKey(
                blank=True,
                db_column='modificado_por',
                help_text='Último usuario operativo que modificó el préstamo.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prestamos_modificados',
                to='api.usuario',
            ),
        ),
    ]
