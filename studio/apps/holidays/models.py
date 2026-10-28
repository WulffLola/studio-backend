from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Holiday(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    class Meta:
        ordering = ['start_date']

    def __str__(self):
        if self.end_date:
            return f"{self.name} ({self.start_date} → {self.end_date})"
        return f"{self.name} ({self.start_date})"
