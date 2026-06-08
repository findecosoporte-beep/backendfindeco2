import django.db.models.deletion
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('api', '0011_prestamo_estado_mysql_varchar'),
    ]

    operations = [
        migrations.CreateModel(
            name='UsuarioRutaCobranzaDia',
            fields=[
                ('id_ruta_dia', models.AutoField(primary_key=True, serialize=False)),
                ('dia_semana', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(6)])),
                ('id_usuario', models.ForeignKey(db_column='id_usuario', on_delete=django.db.models.deletion.CASCADE, related_name='ruta_cobranza_dias', to='api.usuario')),
                ('id_zona', models.ForeignKey(db_column='id_zona', on_delete=django.db.models.deletion.PROTECT, related_name='ruta_cobranza_dias', to='api.zona')),
            ],
            options={
                'db_table': 'usuario_ruta_cobranza_dias',
                'ordering': ['id_usuario_id', 'dia_semana'],
            },
        ),
        migrations.AddConstraint(
            model_name='usuariorutacobranzadia',
            constraint=models.UniqueConstraint(fields=('id_usuario', 'dia_semana'), name='uniq_usuario_ruta_dia_semana'),
        ),
    ]
