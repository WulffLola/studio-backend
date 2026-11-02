from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0005_alter_note_descripcion'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='note',
            name='deleted_at',
        ),
        migrations.AlterField(
            model_name='note',
            name='estado',
            field=models.CharField(
                choices=[
                    ('borrador', 'Borrador'),
                    ('en_pausa', 'En Pausa'),
                    ('activo', 'Activo'),
                ],
                default='borrador',
                max_length=20,
            ),
        ),
    ]
