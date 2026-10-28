from django.db import models
from decimal import Decimal
from apps.users.models import CustomUser
from apps.people.models import Person
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Payment(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    method = models.CharField(max_length=50, null=True, blank=True)
    observation = models.CharField(max_length=100, null=True, blank=True)
    studio = models.ForeignKey('studios.Studio', on_delete=models.PROTECT, related_name='payments')
    deleted = models.DateField(null=True, blank=True)
    pdf_file = models.FileField(upload_to='payments/', null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"{self.person} paid on {self.date}"


class PaymentItem(SoftDeleteMixin):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='items')
    person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_items')
    plans_subtype = models.ForeignKey('plans_subtype.PlansSubtype', on_delete=models.PROTECT, related_name='payment_items')
    base_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    DISCOUNT_SOURCE_CHOICES = [('combo', 'combo'), ('plan', 'plan'), ('none', 'none')]
    discount_source = models.CharField(max_length=10, choices=DISCOUNT_SOURCE_CHOICES, default='none')
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return f"{self.plans_subtype} – ${self.final_amount} (dto {self.discount_pct}%)"

    def save(self, *args, **kwargs):
        self.final_amount = Decimal(str(self.base_amount)) * (1 - Decimal(str(self.discount_pct)) / 100)
        super().save(*args, **kwargs)
