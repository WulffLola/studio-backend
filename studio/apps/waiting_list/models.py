from django.db import models
from django.utils import timezone
from apps.people.models import Person
from apps.slots.models import Slot
from utils import DeletedManager, DeletedQuerySet


class WaitingList(models.Model):
    id = models.AutoField(primary_key=True)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='waitinglist', null=True, blank=True)
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name='waitinglist', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"Waiting list for {self.person}"

    def delete(self, using=None, keep_parents=False):
        self.deleted = timezone.now()
        self.save(update_fields=['deleted'])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted = None
        self.save(update_fields=['deleted'])
