from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0003_alter_personactiveplan_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='profile_photo',
            field=models.ImageField(blank=True, null=True, upload_to='people/photos/'),
        ),
    ]
