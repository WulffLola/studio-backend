from django.db import models
from apps.expense_type.models import ExpenseType
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Expense(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    date = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    type = models.ForeignKey(ExpenseType, on_delete=models.CASCADE, null=True, blank=True)
    method = models.CharField(max_length=50, null=True, blank=True)
    observation = models.CharField(max_length=50, null=True, blank=True)
    studio = models.ForeignKey('studios.Studio', on_delete=models.PROTECT, related_name='expenses')
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"{self.amount} paid on {self.date}"
