from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class PlansType(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(null=True, blank=True, help_text="Cantidad total de clases/sesiones del plan")
    frequency = models.CharField(max_length=50, blank=True, default='', help_text="Frecuencia, ej: 'semanal', '3 veces por semana'")
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return self.name


class ComboPlanDiscount(SoftDeleteMixin):
    # M2M a PlansSubtype: soporta N planes por combo (antes era solo A+B con PlansType)
    name = models.CharField(max_length=100, blank=True, default='')
    plans = models.ManyToManyField(
        'plans_subtype.PlansSubtype',
        related_name='combo_discounts',
    )
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        names = ' + '.join(p.name for p in self.plans.all())
        return f"{names} → {self.discount_pct}%"


class PlanDiscount(SoftDeleteMixin):
    """Descuento aplicable a un único plan (PlansSubtype), independiente de combos."""
    plans_subtype = models.ForeignKey(
        'plans_subtype.PlansSubtype',
        on_delete=models.CASCADE,
        related_name='plan_discounts',
    )
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return f"{self.plans_subtype} → {self.discount_pct}%"
