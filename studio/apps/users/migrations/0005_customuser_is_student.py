from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_customuser_profile_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_student',
            field=models.BooleanField(default=False),
        ),
    ]
