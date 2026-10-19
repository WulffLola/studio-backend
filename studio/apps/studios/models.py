from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Studio(SoftDeleteMixin):
    name = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    # Estado de configuración
    # Requisitos para considerar el estudio "listo" (deben cumplirse todos).
    # Salas / slot templates / slots se cuentan por-estudio (vía room.studio);
    # los catálogos (payment methods, activity types/subtypes, plans
    # type/subtype) son globales y basta con que exista al menos uno.
    # Solo se cuentan registros activos (no borrados lógicamente).
    def config_status(self):
        """Devuelve {requisito: bool} con el estado de cada requisito."""
        from apps.slots.models import SlotTemplate, Slot
        from apps.payment_method.models import PaymentMethod
        from apps.activity_type.models import ActivityType
        from apps.activity_subtype.models import ActivitySubType
        from apps.plans_type.models import PlansType
        from apps.plans_subtype.models import PlansSubtype
        return {
            "rooms": self.rooms.exists(),
            "slot_templates": SlotTemplate.objects.filter(room__studio=self).exists(),
            "slots": Slot.objects.filter(room__studio=self).exists(),
            "payment_methods": PaymentMethod.objects.exists(),
            "activity_types": ActivityType.objects.exists(),
            "activity_subtypes": ActivitySubType.objects.exists(),
            "plans_types": PlansType.objects.exists(),
            "plans_subtypes": PlansSubtype.objects.exists(),
        }

    @property
    def is_ready(self):
        """True solo cuando el estudio tiene TODOS los datos requeridos.

        Reemplaza al antiguo BooleanField manual: ahora se calcula y no se
        puede forzar desde la API.
        """
        return all(self.config_status().values())
