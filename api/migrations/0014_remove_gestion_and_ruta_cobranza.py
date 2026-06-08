"""Elimina modelos de cobranzas (tablas gestion_cobranza y usuario_ruta_cobranza_dias)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_hojacobroimpresion'),
    ]

    operations = [
        migrations.DeleteModel(name='UsuarioRutaCobranzaDia'),
        migrations.DeleteModel(name='GestionCobranza'),
    ]
