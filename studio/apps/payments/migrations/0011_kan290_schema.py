import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0010_kan290_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment', name='amount',
            field=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)),
        migrations.AlterField(
            model_name='payment', name='studio',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                    related_name='payments', to='studios.studio')),
    ]
