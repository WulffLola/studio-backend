from django.db.models import Prefetch

from .models import TeachersTurn


def teachers_turn_prefetch(lookup='teachers_turn'):
    """Prefetch de las asignaciones vivas de docentes de un slot.

    Precarga `lookup` (por defecto 'teachers_turn' para querysets de Slot; usar
    'slot__teachers_turn' para querysets de Appointment) con solo las filas no
    eliminadas y su `teacher` por select_related, de modo que
    SlotSerializer.get_teachers resuelva sin N+1. Se filtra deleted__isnull=True
    en el prefetch y, de nuevo, en Python dentro del serializer (defensa en
    profundidad si el prefetch no se aplicara).
    """
    return Prefetch(
        lookup,
        queryset=TeachersTurn.objects.filter(deleted__isnull=True).select_related('teacher'),
    )
