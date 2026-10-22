from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin

class ActivityType(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='activity_type/photos/', null=True, blank=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return self.name
