from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('slots', '0001_initial'),
        ('activity_subtype', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='slot',
            name='activity_subtype',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='slots',
                to='activity_subtype.activitysubtype',
            ),
        ),
    ]
