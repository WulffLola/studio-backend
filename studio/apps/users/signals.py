from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='users.CustomUser')
def sync_user_identity(sender, instance, created, **kwargs):
    """Para usuarios que actúan como alumno: mantiene una Person vinculada.

    Perfil + dni + email se sincronizan User -> Person. En el alta sin Person, se
    crea una con esos mismos campos.
    """
    from apps.people.models import Person
    from apps.users.identity_sync import (
        sync_user_to_person, profile_values, USER_TO_PERSON_FIELDS,
    )

    if not instance.is_student_user:
        return

    if instance.person_id:
        sync_user_to_person(instance)
    elif created:
        person = Person.objects.create(
            **profile_values(instance, Person, USER_TO_PERSON_FIELDS)
        )
        # update directo: no re-dispara el post_save de CustomUser
        type(instance).objects.filter(pk=instance.pk).update(person=person)
