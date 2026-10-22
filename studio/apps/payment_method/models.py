from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class PaymentMethod(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    amount = models.CharField(max_length=50, null=True, blank=True)
    method = models.CharField(max_length=50, null=True, blank=True)
    plans_subtype = models.ForeignKey(
        'plans_subtype.PlansSubtype',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment_methods',
    )
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return self.method
