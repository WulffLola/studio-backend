from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('people', '0002_person_active_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='person',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='user',
                to='people.person',
            ),
        ),
    ]
