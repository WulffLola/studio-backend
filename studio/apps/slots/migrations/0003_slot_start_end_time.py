from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slots', '0002_slot_activity_subtype'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='slot',
            name='time_slot',
        ),
        migrations.RemoveField(
            model_name='slot',
            name='duration',
        ),
        migrations.AddField(
            model_name='slot',
            name='start_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='slot',
            name='end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='slot',
            options={'ordering': ['week_day', 'start_time']},
        ),
    ]
