from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plans_subtype', '0003_remove_planssubtype_price'),
        ('activity_subtype', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='planssubtype',
            name='activity_subtype',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='plans_subtypes',
                to='activity_subtype.activitysubtype',
            ),
        ),
    ]
