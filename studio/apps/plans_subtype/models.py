from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin
from apps.plans_type.models import PlansType

class PlansSubtype(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    plan_type = models.ForeignKey(PlansType, on_delete=models.CASCADE, related_name='subtypes', db_column='plans_type_id')
    sessions = models.PositiveIntegerField(null=True, blank=True, help_text="Cantidad de clases incluidas en este subplan")
    activity_subtype = models.ForeignKey(
        'activity_subtype.ActivitySubType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plans_subtypes',
    )
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return self.name
