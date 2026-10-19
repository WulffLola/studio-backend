from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('studios', '0002_studio_is_ready'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='studio',
            name='is_ready',
        ),
    ]
