from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('slots', '0004_alter_slot_options_slot_date_slottemplate_and_more'),
        ('weeks', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='slot',
            name='week_day',
        ),
        migrations.AlterModelOptions(
            name='slot',
            options={'ordering': ['date', 'start_time']},
        ),
    ]
