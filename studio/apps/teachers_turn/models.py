from django.db import models
from apps.teachers.models import Teacher
from apps.slots.models import Slot
from apps.teacher_rol.models import Rol
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class TeachersTurn(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='teachers_turn', null=True, blank=True)
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name='teachers_turn', null=True, blank=True)
    is_receptionist = models.BooleanField(null=True, blank=True)
    rol = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"Teacher turn for {self.teacher}"
