from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home_phrase', '0002_rename_text_homephrase_phrase'),
    ]

    operations = [
        migrations.AddField(
            model_name='homephrase',
            name='title',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='homephrase',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
