from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payment_method', '0002_paymentmethod_plans_subtype'),
    ]

    operations = [
        migrations.RemoveField(model_name='paymentmethod', name='plan'),
    ]
