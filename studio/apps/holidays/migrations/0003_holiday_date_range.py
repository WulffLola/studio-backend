from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Reemplaza el campo 'date' (un solo día) por 'start_date' + 'end_date' opcional
    para soportar tanto feriados de un día como rangos (ej: vacaciones).
    También elimina la UniqueConstraint sobre 'date', que ya no aplica.
    """

    dependencies = [
        ('holidays', '0002_unique_date_active'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='holiday',
            name='uniq_holiday_date_active',
        ),
        migrations.RenameField(
            model_name='holiday',
            old_name='date',
            new_name='start_date',
        ),
        migrations.AddField(
            model_name='holiday',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='holiday',
            options={'ordering': ['start_date']},
        ),
    ]
