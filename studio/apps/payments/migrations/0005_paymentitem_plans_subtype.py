from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_alter_paymentitem_id'),
        ('plans_subtype', '0005_planssubtype_prices'),
    ]

    operations = [
        migrations.RenameField(
            model_name='paymentitem',
            old_name='plans_type',
            new_name='plans_subtype',
        ),
        migrations.AlterField(
            model_name='paymentitem',
            name='plans_subtype',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payment_items',
                to='plans_subtype.planssubtype',
            ),
        ),
    ]
