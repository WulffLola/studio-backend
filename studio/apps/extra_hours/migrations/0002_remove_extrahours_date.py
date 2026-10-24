from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extra_hours', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='extrahours',
            name='date',
        ),
    ]
