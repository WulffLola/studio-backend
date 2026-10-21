from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0006_person_firmo_declaracion_general'),
    ]

    operations = [
        migrations.RemoveField(model_name='person', name='plan'),
    ]
