from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sworn_statement', '0002_appointmentswornstatement'),
    ]

    operations = [
        migrations.AddField(
            model_name='swornstatement',
            name='statement_type',
            field=models.CharField(
                choices=[('person', 'Persona'), ('appointment', 'Turno')],
                default='person',
                max_length=20,
            ),
        ),
    ]
