import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0026_usuario_clave_deprecada'),
    ]

    operations = [
        migrations.CreateModel(
            name='UsuarioCartera',
            fields=[
                ('id_usuario_cartera', models.AutoField(primary_key=True, serialize=False)),
                (
                    'id_cartera',
                    models.ForeignKey(
                        db_column='id_cartera',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cobradores_asignados',
                        to='api.cartera',
                    ),
                ),
                (
                    'id_usuario',
                    models.ForeignKey(
                        db_column='id_usuario',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='carteras_asignadas',
                        to='api.usuario',
                    ),
                ),
            ],
            options={
                'db_table': 'usuario_carteras',
                'ordering': ['id_cartera_id'],
            },
        ),
        migrations.AddConstraint(
            model_name='usuariocartera',
            constraint=models.UniqueConstraint(
                fields=('id_cartera',),
                name='uniq_cartera_un_cobrador',
            ),
        ),
    ]
