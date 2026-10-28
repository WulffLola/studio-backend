from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_initial'),
        ('plans_type', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('base_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('discount_pct', models.DecimalField(
                    decimal_places=2, default=Decimal('0'), max_digits=5,
                )),
                ('final_amount', models.DecimalField(decimal_places=2, editable=False, max_digits=10)),
                ('deleted', models.DateField(blank=True, null=True)),
                ('payment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='payments.payment',
                )),
                ('plans_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='payment_items',
                    to='plans_type.planstype',
                )),
            ],
        ),
    ]
