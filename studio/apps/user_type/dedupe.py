"""Deduplicación del tipo de usuario 'Student' -> 'Estudiante'.

La lógica vive acá (y no inline en la migración) para poder testearla directo.
Usa ``apps.get_model`` para ser histórica-segura: la migración le pasa el registro
histórico; los tests le pasan el registro real (``django.apps.apps``).
"""


def merge_duplicate_student_type(apps, schema_editor=None):
    """Unifica la fila duplicada 'Student' en la canónica 'Estudiante'.

    Reasigna los ``CustomUser`` que apunten a 'Student' hacia 'Estudiante' y borra
    la fila 'Student'. Crea 'Estudiante' si no existe. Es no-op si no hay 'Student'.
    Devuelve la cantidad de usuarios reasignados.
    """
    UserType = apps.get_model('user_type', 'UserType')
    CustomUser = apps.get_model('users', 'CustomUser')

    duplicate = UserType.objects.filter(user_type_name='Student').first()
    if duplicate is None:
        return 0

    estudiante, _ = UserType.objects.get_or_create(user_type_name='Estudiante')
    if duplicate.pk == estudiante.pk:
        return 0

    # Reasignar con el manager MÁS amplio disponible: si se usara `objects`
    # (filtrado por deleted en el registro real), los usuarios soft-deleted no se
    # reasignarían y el cascade de on_delete al borrar 'Student' los HARD-borraría.
    # En el registro histórico de la migración `all_objects` no existe -> cae en
    # `objects`, que ahí no filtra por deleted (los managers no son use_in_migrations).
    manager = getattr(CustomUser, 'all_objects', CustomUser.objects)
    reassigned = manager.filter(tipo_usuario=duplicate).update(
        tipo_usuario=estudiante,
    )
    duplicate.delete()
    return reassigned


def recreate_student_type(apps, schema_editor=None):
    """Reverse: recrea la fila 'Student' (simetría de schema). La reasignación de
    usuarios no se revierte."""
    UserType = apps.get_model('user_type', 'UserType')
    UserType.objects.get_or_create(user_type_name='Student')
