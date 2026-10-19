from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Room(SoftDeleteMixin):
    studio = models.ForeignKey("studios.Studio", on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=120)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    class Meta:
        ordering = ["studio__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["studio", "name"], name="uniq_room_name_per_studio"),
        ]
        indexes = [
            models.Index(fields=["studio", "name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} @ {self.studio.name}"
