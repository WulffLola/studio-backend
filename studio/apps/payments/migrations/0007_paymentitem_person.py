from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0006_payment_studio'),
        ('people', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentitem',
            name='person',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payment_items',
                to='people.person',
            ),
        ),
    ]
