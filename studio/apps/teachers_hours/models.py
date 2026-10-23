from django.db import models
from apps.teachers.models import Teacher
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Hour(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='teacher_hour', null=True, blank=True)
    month = models.CharField(max_length=50, null=True, blank=True)
    hour = models.CharField(max_length=50, null=True, blank=True)
    extra_hour = models.CharField(max_length=50, null=True, blank=True)
    total = models.CharField(max_length=50, null=True, blank=True)
    left = models.CharField(max_length=50, null=True, blank=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"{self.teacher} - {self.month}"
