from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('studios', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='studio',
            name='is_ready',
            field=models.BooleanField(default=False, help_text='True cuando el estudio está completamente configurado'),
        ),
    ]
