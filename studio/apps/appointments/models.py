from django.db import models
from apps.people.models import Person
from apps.slots.models import Slot
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Appointment(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='appointments', null=True, blank=True)
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name='appointments', null=True, blank=True)
    fixed_slot = models.ForeignKey(
        'slots.FixedSlot', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments',
    )
    consumed_plan = models.ForeignKey(
        'people.PersonActivePlan', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='consumed_appointments',
    )
    reserved = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted = models.DateTimeField(null=True, blank=True)
    firmo_declaracion_clase = models.BooleanField(default=False)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"Appointment for {self.person}"
