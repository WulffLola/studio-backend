from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('plans_subtype', '0002_planssubtype_price'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='planssubtype',
            name='price',
        ),
    ]
