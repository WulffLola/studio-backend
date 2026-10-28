from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0005_paymentitem_plans_subtype'),
        ('studios', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='studio',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payments',
                to='studios.studio',
            ),
        ),
    ]
