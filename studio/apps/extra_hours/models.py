from django.db import models
from apps.teachers.models import Teacher
from apps.slots.models import Slot
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class ExtraHours(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='extra_hour', null=True, blank=True)
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name='extra_hour', null=True, blank=True)
    price = models.FloatField(default=0)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"Extra Hour for {self.teacher}"
