from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sworn_statement', '0001_initial'),
        ('appointments', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentSwornStatement',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('signed_at', models.DateTimeField(auto_now_add=True)),
                ('appointment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sworn_statements',
                    to='appointments.appointment',
                )),
                ('statement', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='class_signers',
                    to='sworn_statement.swornstatement',
                )),
            ],
            options={
                'ordering': ['-signed_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='appointmentswornstatement',
            unique_together={('appointment', 'statement')},
        ),
    ]
