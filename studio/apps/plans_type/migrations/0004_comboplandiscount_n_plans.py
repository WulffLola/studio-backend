from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Reemplaza los dos ForeignKeys fijos (plan_type_a, plan_type_b -> PlansType)
    por un ManyToMany (plans -> PlansSubtype) para soportar N planes por combo.
    """

    dependencies = [
        ('plans_type', '0003_alter_comboplandiscount_id'),
        ('plans_subtype', '0002_planssubtype_price'),
    ]

    operations = [
        # 1. Quitar la restricción de unicidad sobre los dos FKs
        migrations.RemoveConstraint(
            model_name='comboplandiscount',
            name='uniq_combo_plan_discount',
        ),
        # 2. Quitar los dos ForeignKeys fijos
        migrations.RemoveField(
            model_name='comboplandiscount',
            name='plan_type_a',
        ),
        migrations.RemoveField(
            model_name='comboplandiscount',
            name='plan_type_b',
        ),
        # 3. Agregar M2M a PlansSubtype
        migrations.AddField(
            model_name='comboplandiscount',
            name='plans',
            field=models.ManyToManyField(
                related_name='combo_discounts',
                to='plans_subtype.planssubtype',
            ),
        ),
    ]
