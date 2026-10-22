from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plans_subtype', '0001_initial'),
        ('payment_method', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentmethod',
            name='plans_subtype',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payment_methods',
                to='plans_subtype.planssubtype',
            ),
        ),
    ]
