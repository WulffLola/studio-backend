from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0001_initial'),
        ('payments', '0008_remove_payment_plan'),
        ('people', '0007_remove_person_plan'),
        ('payment_method', '0003_remove_paymentmethod_plan'),
    ]

    operations = [
        migrations.DeleteModel(name='Plan'),
    ]
