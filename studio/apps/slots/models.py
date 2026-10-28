from django.db import models, transaction
from django.utils import timezone
from apps.weeks.models import Week
from apps.status.models import Status
from apps.rooms.models import Room
from apps.activity_subtype.models import ActivitySubType
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class SlotTemplate(SoftDeleteMixin):
    """
    Define la regla de recurrencia: qué días de la semana, horario,
    sala y actividad. Los Slot individuales (occurrences) se generan
    a partir de este template para un rango de fechas concreto.
    """
    days_of_week = models.ManyToManyField(Week, related_name='templates', blank=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(Room, on_delete=models.CASCADE, null=True, blank=True, related_name='slot_templates')
    activity_subtype = models.ForeignKey(ActivitySubType, on_delete=models.PROTECT, null=True, blank=True, related_name='slot_templates')
    availability = models.IntegerField()
    is_active = models.BooleanField(default=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        days = ', '.join(str(d) for d in self.days_of_week.all())
        return f"Template [{days}] {self.start_time}-{self.end_time}"

    def delete(self, using=None, keep_parents=False):
        with transaction.atomic():
            self.deleted = timezone.now().date()
            self.save(update_fields=['deleted'])
            # Cascade: soft-delete de los FixedSlot activos de este template
            self.fixed_slots.filter(deleted__isnull=True).update(deleted=self.deleted)

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted = None
        self.save(update_fields=['deleted'])


class Slot(SoftDeleteMixin):
    id = models.AutoField(primary_key=True)
    template = models.ForeignKey(SlotTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='occurrences')
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    status = models.ForeignKey(Status, on_delete=models.PROTECT, related_name='slot', null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="slots", null=True, blank=True)
    activity_subtype = models.ForeignKey(ActivitySubType, on_delete=models.PROTECT, related_name='slots', null=True, blank=True)
    availability = models.IntegerField(null=True, blank=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()                  # solo no eliminados (default)
    all_objects = DeletedQuerySet.as_manager()  # todos, con .alive() y .dead()

    class Meta:
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.date} {self.start_time} - {self.end_time}"


class FixedSlot(SoftDeleteMixin):
    """
    Turno fijo: una persona reserva un SlotTemplate de forma recurrente.
    Representa el compromiso de asistir a esa clase cada semana.
    """
    person = models.ForeignKey(
        'people.Person',
        on_delete=models.CASCADE,
        related_name='fixed_slots',
    )
    template = models.ForeignKey(
        SlotTemplate,
        on_delete=models.CASCADE,
        related_name='fixed_slots',
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    observation = models.CharField(max_length=250, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.DateField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    class Meta:
        ordering = ['template__start_time']
        unique_together = [('person', 'template')]

    def __str__(self):
        return f"{self.person} – turno fijo {self.template}"

    def covers(self, d):
        """True si la fecha `d` cae dentro de la vigencia del turno fijo."""
        if d < self.start_date:
            return False
        return self.end_date is None or d <= self.end_date

    def reserve_existing_slots(self):
        """
        Materializa reservas sobre los Slots existentes del template dentro de
        [start_date, end_date]. Devuelve (reservas_creadas, warnings). Cada slot lleno
        agrega un warning {date, slot, reason:"slot_lleno"}. Ver reserve_person_in_slot.
        """
        slots = Slot.objects.filter(template=self.template, date__gte=self.start_date)
        if self.end_date is not None:
            slots = slots.filter(date__lte=self.end_date)
        creadas, warnings = 0, []
        for slot in slots:
            estado = reserve_person_in_slot(self.person, slot, self)
            if estado == "creado":
                creadas += 1
            elif estado in ("slot_lleno", "sin_sesiones"):
                warnings.append({"date": slot.date.isoformat(), "slot": slot.id, "reason": estado})
        return creadas, warnings

    def delete(self, using=None, keep_parents=False):
        """Soft-delete del turno fijo + cancelación de sus reservas futuras
        automáticas (soft-delete del Appointment y devolución de availability al
        slot). No toca reservas pasadas ni manuales (fixed_slot NULL)."""
        from apps.appointments.models import Appointment
        with transaction.atomic():
            super().delete(using=using, keep_parents=keep_parents)  # soft-delete (SoftDeleteMixin)
            hoy = timezone.now().date()
            futuras = Appointment.objects.filter(
                fixed_slot=self, slot__date__gte=hoy, deleted__isnull=True,
            ).select_related('slot', 'consumed_plan')
            for appt in futuras:
                slot = appt.slot
                appt.delete()
                if appt.consumed_plan_id and appt.consumed_plan and appt.consumed_plan.deleted is None:
                    appt.consumed_plan.restore_session()
                if slot is not None:
                    slot.availability = (slot.availability or 0) + 1
                    if slot.status_id == STATUS_LLENO:
                        slot.status_id = STATUS_DISPONIBLE
                    slot.save(update_fields=['availability', 'status'])


# Reserva de turnos fijos

# Ids de Status usados en todo el módulo (coinciden con appointments/views.py).
STATUS_DISPONIBLE = 1
STATUS_LLENO = 2


def reserve_person_in_slot(person, slot, fixed_slot):
    """
    Crea una reserva confirmada (Appointment con reserved=False; el flag `reserved`
    se usa para lista de espera/notificación en otros flujos, no para turnos fijos)
    de `person` en `slot`, vinculada a `fixed_slot`. Replica la semántica de
    AppointmentsViewSet.create: decrementa `availability` y marca LLENO al llegar a 0.

    Devuelve el estado: "creado", "slot_lleno" (sin cupo -> advertencia) o
    "ya_reservado" (idempotencia; no es advertencia).
    """
    from apps.appointments.models import Appointment
    from apps.people.selectors import find_consumable_plan, person_has_plan_for_activity

    if slot.availability is None or slot.availability <= 0 or slot.status_id == STATUS_LLENO:
        return "slot_lleno"

    if Appointment.objects.filter(slot=slot, person=person, deleted__isnull=True).exists():
        return "ya_reservado"

    plan = find_consumable_plan(person, slot)
    if plan is None and person_has_plan_for_activity(person, slot):
        return "sin_sesiones"

    with transaction.atomic():
        # descontar la sesión ANTES de crear el turno, de forma atómica.
        # Si otra reserva concurrente se llevó la última, deduct_session() devuelve
        # False y abortamos sin crear turno ni tocar el slot.
        if plan is not None and not plan.deduct_session():
            return "sin_sesiones"
        Appointment.objects.create(
            person=person, slot=slot, reserved=False, fixed_slot=fixed_slot,
            consumed_plan=plan,
        )
        slot.availability -= 1
        if slot.availability == 0:
            slot.status_id = STATUS_LLENO
        slot.save(update_fields=['availability', 'status'])
    return "creado"
