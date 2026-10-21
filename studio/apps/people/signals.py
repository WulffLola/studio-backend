from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='people.Person')
def sync_person_identity(sender, instance, created, update_fields=None, **kwargs):
    """Propaga los campos de perfil de la Person a sus Users vinculados.

    No corre si la Person está soft-deleted, ni si el save declara update_fields
    que no incluyen ningún campo de perfil.
    """
    from apps.users.identity_sync import sync_person_to_users, PROFILE_FIELDS
    if instance.deleted:
        return
    if update_fields is not None and not (set(update_fields) & set(PROFILE_FIELDS)):
        return
    sync_person_to_users(instance)
