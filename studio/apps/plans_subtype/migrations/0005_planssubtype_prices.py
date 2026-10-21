from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plans_subtype', '0004_planssubtype_activity_subtype'),
    ]

    operations = [
        migrations.AddField(
            model_name='planssubtype',
            name='price_cash',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='planssubtype',
            name='price_transfer',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
