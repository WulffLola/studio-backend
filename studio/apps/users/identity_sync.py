"""Sincronización de datos compartidos entre CustomUser y Person.

CustomUser es la fuente de verdad de las credenciales. Los campos de perfil se
sincronizan en ambas direcciones; el dni y el email solo bajan User -> Person
(nunca suben). La copia se hace con .update() sobre el lado opuesto para NO
disparar el post_save contrario y evitar recursión.
"""
from apps.people.models import Person
from apps.users.models import CustomUser

# Perfil: sincronización bidireccional User <-> Person.
PROFILE_FIELDS = ["name", "last_name", "phone", "sex", "birth_date", "profile_photo"]

# User -> Person: perfil + dni + email (dni y email solo bajan, nunca suben).
USER_TO_PERSON_FIELDS = PROFILE_FIELDS + ["dni", "email"]


def profile_values(source_obj, target_model, fields):
    """Valores de `fields` de `source_obj` listos para escribir en `target_model`.

    Ajusta cada valor a las restricciones de la columna destino:
      - profile_photo -> path almacenado (.name) o ''.
      - None -> '' para columnas char NOT NULL del destino.
      - se trunca a max_length del destino.
    """
    values = {}
    for field in fields:
        value = getattr(source_obj, field)
        if field == "profile_photo":
            values[field] = value.name if value else ""
            continue
        target_field = target_model._meta.get_field(field)
        if value is None and not target_field.null:
            value = ""
        max_length = getattr(target_field, "max_length", None)
        if isinstance(value, str) and max_length and len(value) > max_length:
            value = value[:max_length]
        values[field] = value
    return values


def sync_user_to_person(user):
    """Propaga perfil + dni + email del user a su Person vinculada (si existe)."""
    if not user.person_id:
        return
    Person.all_objects.filter(pk=user.person_id).update(
        **profile_values(user, Person, USER_TO_PERSON_FIELDS)
    )


def sync_person_to_users(person):
    """Propaga los campos de perfil de la person a sus Users vinculados.

    Nunca escribe dni/email: las credenciales de login solo cambian desde el User.
    """
    CustomUser.all_objects.filter(person_id=person.pk).update(
        **profile_values(person, CustomUser, PROFILE_FIELDS)
    )


def find_identity_mismatches():
    """Pares vinculados desalineados en perfil+dni+email:
    [(user, person, [campos_divergentes]), ...].

    Trata None y '' como equivalentes.
    """
    mismatches = []
    qs = CustomUser.all_objects.filter(person__isnull=False).select_related("person")
    for user in qs:
        person = user.person
        diverging = []
        for field in USER_TO_PERSON_FIELDS:
            uval = getattr(user, field)
            pval = getattr(person, field)
            if field == "profile_photo":
                uval = uval.name if uval else ""
                pval = pval.name if pval else ""
            else:
                uval = "" if uval is None else uval
                pval = "" if pval is None else pval
            if uval != pval:
                diverging.append(field)
        if diverging:
            mismatches.append((user, person, diverging))
    return mismatches
