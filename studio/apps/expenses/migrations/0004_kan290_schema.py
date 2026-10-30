import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0003_kan290_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expense', name='amount',
            field=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)),
        migrations.AlterField(
            model_name='expense', name='studio',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                    related_name='expenses', to='studios.studio')),
    ]
