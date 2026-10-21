from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plans_type', '0005_planstype_quantity_frequency'),
    ]

    operations = [
        migrations.AddField(
            model_name='comboplandiscount',
            name='name',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
