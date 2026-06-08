"""Carteras operativas (nombre y día de cobro)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_cliente_campos_formulario'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cartera',
            fields=[
                ('id_cartera', models.AutoField(primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=120)),
                ('dia_cobro', models.CharField(max_length=40)),
            ],
            options={
                'db_table': 'carteras',
                'ordering': ['nombre'],
            },
        ),
    ]
