from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Status(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    status = models.CharField(null=True, blank=True, max_length=50)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return self.status
