from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recipes', '0006_alter_recipe_descripcion'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='recipe',
            name='deleted_at',
        ),
        migrations.AlterField(
            model_name='recipe',
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
