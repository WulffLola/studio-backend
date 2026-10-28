from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slots', '0005_remove_slot_week_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='slottemplate',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
