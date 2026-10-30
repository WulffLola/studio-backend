from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0001_initial'),
        ('studios', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='studio',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='expenses',
                to='studios.studio',
            ),
        ),
    ]
