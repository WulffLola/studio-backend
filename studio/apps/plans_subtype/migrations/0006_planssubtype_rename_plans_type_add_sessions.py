from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plans_subtype', '0005_planssubtype_prices'),
        ('plans_type', '0005_planstype_quantity_frequency'),
    ]

    operations = [
        migrations.RenameField(
            model_name='planssubtype',
            old_name='plans_type',
            new_name='plan_type',
        ),
        migrations.AddField(
            model_name='planssubtype',
            name='sessions',
            field=models.PositiveIntegerField(blank=True, null=True, help_text='Cantidad de clases incluidas en este subplan'),
        ),
    ]
