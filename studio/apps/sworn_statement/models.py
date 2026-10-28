from django.db import models
from utils import DeletedManager, DeletedQuerySet, SoftDeleteMixin


class SwornStatement(SoftDeleteMixin):
    """
    Texto de la declaración jurada que el estudio configura.
    Puede haber múltiples versiones; la activa (is_active=True) es única por
    statement_type: a lo sumo una general (person) y una de clase (appointment).
    """
    STATEMENT_TYPE_PERSON = 'person'
    STATEMENT_TYPE_APPOINTMENT = 'appointment'
    STATEMENT_TYPE_CHOICES = [
        (STATEMENT_TYPE_PERSON, 'Persona'),
        (STATEMENT_TYPE_APPOINTMENT, 'Turno'),
    ]

    id = models.AutoField(primary_key=True)
    text = models.TextField()
    statement_type = models.CharField(
        max_length=20,
        choices=STATEMENT_TYPE_CHOICES,
        default=STATEMENT_TYPE_PERSON,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = DeletedManager()
    all_objects = DeletedQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['statement_type'],
                condition=models.Q(is_active=True, deleted__isnull=True),
                name='uniq_active_sworn_por_tipo',
            )
        ]

    def __str__(self):
        return f"Declaración jurada #{self.id} ({self.created_at.date() if self.created_at else '—'})"


class PersonSwornStatement(models.Model):
    """
    Registro de que una persona aceptó una declaración jurada específica.
    """
    id = models.AutoField(primary_key=True)
    person = models.ForeignKey(
        'people.Person',
        on_delete=models.CASCADE,
        related_name='sworn_statements',
    )
    statement = models.ForeignKey(
        SwornStatement,
        on_delete=models.PROTECT,
        related_name='signers',
    )
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-signed_at']

    def __str__(self):
        return f"{self.person} — firmó declaración #{self.statement_id}"


class AppointmentSwornStatement(models.Model):
    """
    Declaración jurada firmada para una clase específica (appointment).
    Se crea cuando el alumno acepta los términos al reservar o al presentarse.
    """
    id = models.AutoField(primary_key=True)
    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.CASCADE,
        related_name='sworn_statements',
    )
    statement = models.ForeignKey(
        SwornStatement,
        on_delete=models.PROTECT,
        related_name='class_signers',
    )
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-signed_at']
        unique_together = [('appointment', 'statement')]

    def __str__(self):
        return f"Appointment #{self.appointment_id} — declaración #{self.statement_id}"
