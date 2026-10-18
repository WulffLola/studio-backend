from django.db import models
from apps.users.models import CustomUser
from django.contrib.postgres.fields import ArrayField
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Action(SoftDeleteMixin):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=50, null=True, blank=True)
    target = models.CharField(max_length=50, null=True, blank=True)
    target_id = models.CharField(max_length=50, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    old_value = ArrayField(models.JSONField(), default=list)
    new_value = ArrayField(models.JSONField(), default=list)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()


    def __str__(self):
        return f"{self.user} performed {self.action} on {self.target} (id: {self.target_id}) at {self.timestamp}"
