from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0034_prestamo_auditoria'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='registrado_por',
            field=models.ForeignKey(
                blank=True,
                db_column='registrado_por',
                help_text='Usuario operativo que registró el cobro (web o app móvil).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pagos_registrados',
                to='api.usuario',
            ),
        ),
    ]
