from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plans_type', '0004_comboplandiscount_n_plans'),
    ]

    operations = [
        migrations.AddField(
            model_name='planstype',
            name='quantity',
            field=models.PositiveIntegerField(blank=True, null=True, help_text='Cantidad total de clases/sesiones del plan'),
        ),
        migrations.AddField(
            model_name='planstype',
            name='frequency',
            field=models.CharField(blank=True, default='', max_length=50, help_text="Frecuencia, ej: 'semanal', '3 veces por semana'"),
        ),
    ]
