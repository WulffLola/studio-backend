from django.utils import timezone

from .models import PersonActivePlan


def find_consumable_plan(person, slot):
    """PersonActivePlan a consumir para reservar `slot`, o None.

    Match por actividad (plans_subtype.activity_subtype == slot.activity_subtype),
    vigente, no borrado y con sesiones; se elige el de exp_date más próximo.
    """
    if slot.activity_subtype_id is None:
        return None
    today = timezone.now().date()
    return PersonActivePlan.objects.filter(
        person=person,
        plans_subtype__activity_subtype_id=slot.activity_subtype_id,
        exp_date__gte=today,
        sessions_remaining__gt=0,
        deleted__isnull=True,
    ).order_by('exp_date').first()


def person_has_plan_for_activity(person, slot):
    """True si la persona tiene un plan vigente para la actividad del slot,
    aunque no le queden sesiones (para distinguir 'sin sesiones' de 'sin plan')."""
    if slot.activity_subtype_id is None:
        return False
    today = timezone.now().date()
    return PersonActivePlan.objects.filter(
        person=person,
        plans_subtype__activity_subtype_id=slot.activity_subtype_id,
        exp_date__gte=today,
        deleted__isnull=True,
    ).exists()
