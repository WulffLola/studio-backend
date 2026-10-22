from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('activity_subtype', '0001_initial'),
        ('plans_type', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='activitysubtype',
            name='plans_type',
        ),
    ]
