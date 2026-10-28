from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0008_remove_payment_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentitem',
            name='discount_source',
            field=models.CharField(choices=[('combo', 'combo'), ('plan', 'plan'), ('none', 'none')], default='none', max_length=10),
        ),
    ]
