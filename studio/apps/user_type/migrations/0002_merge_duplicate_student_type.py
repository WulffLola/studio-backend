"""Elimina el tipo de usuario duplicado 'Student', unificándolo en 'Estudiante'.

Reasigna los usuarios que tuvieran 'Student' hacia 'Estudiante' y borra la fila.
Es idempotente/segura aunque la fila no exista (no-op).
"""
from django.db import migrations

from apps.user_type.dedupe import merge_duplicate_student_type, recreate_student_type


class Migration(migrations.Migration):

    dependencies = [
        ('user_type', '0001_initial'),
        ('users', '0006_customuser_phone_birth_date_sex'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_student_type, recreate_student_type),
    ]
