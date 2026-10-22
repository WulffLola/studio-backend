from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin
from apps.activity_type.models import ActivityType

class ActivitySubType(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE, related_name='subtypes')
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return self.name
