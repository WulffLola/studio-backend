from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('plans_subtype', '0007_alter_planssubtype_plan_type'),
    ]

    operations = [
        migrations.RemoveField(model_name='planssubtype', name='price_cash'),
        migrations.RemoveField(model_name='planssubtype', name='price_transfer'),
    ]
