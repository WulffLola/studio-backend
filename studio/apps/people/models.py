from django.db import models, transaction
from django.utils import timezone
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class Person(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50, null=True, blank=True)
    sex = models.CharField(max_length=50, null=True, blank=True)
    dni = models.CharField(max_length=8, null=True, blank=True)
    email = models.EmailField(max_length=50, null=True, blank=True)
    phone = models.CharField(max_length=11, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    observation = models.CharField(max_length=250, null=True, blank=True)
    last_payment = models.DateField(null=True, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    profile_photo = models.ImageField(upload_to='people/photos/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)
    firmo_declaracion_general = models.BooleanField(default=False)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    def __str__(self):
        return f"{self.name} {self.last_name}"

    def delete(self, using=None, keep_parents=False):
        with transaction.atomic():
            self.deleted = timezone.now()
            self.save(update_fields=['deleted'])
            # Cascade: soft-delete de los FixedSlot activos de esta persona
            today = timezone.now().date()
            self.fixed_slots.filter(deleted__isnull=True).update(deleted=today)

    # hard_delete() se hereda de SoftDeleteMixin: allí super() es models.Model,
    # así que borra la fila de verdad. No sobrescribir acá, porque el super() de
    # Person es SoftDeleteMixin y super().delete() haría un soft-delete.

    def restore(self):
        self.deleted = None
        self.save(update_fields=['deleted'])

    def has_active_plan(self):
        """True si la persona tiene al menos un PersonActivePlan vigente
        (no vencido y con sesiones). Ver PersonActivePlan.is_active."""
        today = timezone.now().date()
        return self.active_plans.filter(
            exp_date__gte=today, sessions_remaining__gt=0,
        ).exists()

    def latest_coverage_end(self):
        """Fecha de fin de cobertura más reciente de la persona, considerando
        tanto los turnos de prueba (Person.exp_date) como los planes pagos
        (PersonActivePlan.exp_date). Devuelve None si no tiene ninguna.
        `active_plans` ya excluye los planes soft-deleted (DeletedManager)."""
        dates = []
        if self.exp_date:
            dates.append(self.exp_date)
        plan_max = self.active_plans.aggregate(m=models.Max('exp_date'))['m']
        if plan_max:
            dates.append(plan_max)
        return max(dates) if dates else None


class PersonActivePlan(SoftDeleteMixin):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='active_plans')
    plans_subtype = models.ForeignKey('plans_subtype.PlansSubtype', on_delete=models.PROTECT, related_name='active_plans')
    exp_date = models.DateField()
    sessions_total = models.IntegerField()
    sessions_remaining = models.IntegerField()
    # Fecha de contratación del plan. Habilita medir renovaciones
    # vincular un plan con el siguiente del mismo alumno+actividad por fecha.
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    def __str__(self):
        return f"{self.person} – {self.plans_subtype} (vence {self.exp_date})"

    def is_active(self):
        today = timezone.now().date()
        return self.exp_date >= today and self.sessions_remaining > 0

    def deduct_session(self):
        """Descuenta una sesión de forma atómica y race-safe: UPDATE condicional
        (solo si sessions_remaining > 0). Devuelve True si descontó, False si ya no
        quedaban sesiones (otra reserva concurrente se llevó la última). Nunca deja
        sessions_remaining negativo."""
        updated = PersonActivePlan.objects.filter(
            pk=self.pk, sessions_remaining__gt=0,
        ).update(sessions_remaining=models.F('sessions_remaining') - 1)
        if updated:
            self.sessions_remaining -= 1  # mantener la instancia en memoria consistente
            return True
        return False

    def restore_session(self):
        """Devuelve una sesión de forma atómica (UPDATE con F()). Evita la race
        inversa a deduct_session: un read-modify-write con un valor absoluto
        calculado sobre una instancia vieja pisaría descuentos concurrentes y
        regalaría sesiones."""
        PersonActivePlan.objects.filter(pk=self.pk).update(
            sessions_remaining=models.F('sessions_remaining') + 1,
        )
        self.sessions_remaining += 1  # instancia en memoria consistente
