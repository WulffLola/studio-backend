from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Teacher(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50, null=True, blank=True)
    sex = models.CharField(max_length=50, null=True, blank=True)
    dni = models.CharField(max_length=8, null=True, blank=True)
    email = models.EmailField(max_length=50, null=True, blank=True)
    phone = models.CharField(max_length=11, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    last_payment = models.DateField(null=True, blank=True)
    hours = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"{self.name} {self.last_name}"
