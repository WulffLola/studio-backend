from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0001_initial'),
        ('plans_type', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PersonActivePlan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('exp_date', models.DateField()),
                ('sessions_total', models.IntegerField()),
                ('sessions_remaining', models.IntegerField()),
                ('deleted', models.DateField(blank=True, null=True)),
                ('person', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='active_plans',
                    to='people.person',
                )),
                ('plans_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='active_plans',
                    to='plans_type.planstype',
                )),
            ],
        ),
    ]
