from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0004_person_profile_photo'),
        ('plans_subtype', '0005_planssubtype_prices'),
    ]

    operations = [
        migrations.RenameField(
            model_name='personactiveplan',
            old_name='plans_type',
            new_name='plans_subtype',
        ),
        migrations.AlterField(
            model_name='personactiveplan',
            name='plans_subtype',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='active_plans',
                to='plans_subtype.planssubtype',
            ),
        ),
    ]
