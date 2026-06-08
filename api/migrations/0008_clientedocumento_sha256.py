from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_prestamocuota'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientedocumento',
            name='sha256',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
