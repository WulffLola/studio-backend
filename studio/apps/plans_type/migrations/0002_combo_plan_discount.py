from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plans_type', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComboPlanDiscount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('discount_pct', models.DecimalField(decimal_places=2, max_digits=5)),
                ('deleted', models.DateField(blank=True, null=True)),
                ('plan_type_a', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='combo_as_a',
                    to='plans_type.planstype',
                )),
                ('plan_type_b', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='combo_as_b',
                    to='plans_type.planstype',
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name='comboplandiscount',
            constraint=models.UniqueConstraint(
                fields=['plan_type_a', 'plan_type_b'],
                name='uniq_combo_plan_discount',
            ),
        ),
    ]
