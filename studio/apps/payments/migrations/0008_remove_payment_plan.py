from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0007_paymentitem_person'),
    ]

    operations = [
        migrations.RemoveField(model_name='payment', name='plan'),
    ]
