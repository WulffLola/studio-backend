from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Week(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    day = models.CharField(max_length=50, null=True, blank=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return self.day
