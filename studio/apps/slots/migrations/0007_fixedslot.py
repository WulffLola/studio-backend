from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('slots', '0006_slottemplate_is_active'),
        ('people', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FixedSlot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('observation', models.CharField(blank=True, default='', max_length=250)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('deleted', models.DateField(blank=True, null=True)),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fixed_slots', to='people.person')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fixed_slots', to='slots.slottemplate')),
            ],
            options={
                'ordering': ['template__start_time'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='fixedslot',
            unique_together={('person', 'template')},
        ),
    ]
