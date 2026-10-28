import logging
from datetime import date, timedelta

from django.db import transaction

from .models import Slot, FixedSlot, reserve_person_in_slot

logger = logging.getLogger(__name__)


def capacity_exceeded_message(availability, room_id):
    """Valida la disponibilidad contra la capacidad de la sala. Devuelve un mensaje
    (str) si es inválida o la supera; None si está OK. Fuente única de la validación
    de capacidad, usable sin DRF — la usa el endpoint (envuelto en Response)
    y el command generate_slots."""
    if availability is None:
        return None
    try:
        availability = int(availability)
    except (TypeError, ValueError):
        return "La disponibilidad debe ser un número entero."
    if availability < 0:
        return "La disponibilidad no puede ser negativa."
    if room_id is None:
        return None
    from apps.rooms.models import Room
    try:
        room = Room.objects.get(pk=room_id)
    except Room.DoesNotExist:
        return None
    if room.capacity is not None and availability > room.capacity:
        return (f"La disponibilidad ({availability}) no puede superar "
                f"la capacidad de la sala ({room.capacity}).")
    return None

# Mapeo canónico Python weekday() -> nombre en español usado en el modelo Week.
WEEKDAY_NAMES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def cancel_unreserved_slots_on_dates(dates, floor=None):
    """Cancela (soft-delete) los ``Slot`` activos que caen en ``dates`` y no
    tienen reservas, protegiendo los que sí las tienen.

    - ``dates``: iterable de ``date`` (típicamente fechas de feriado).
    - ``floor``: solo se afectan slots con ``date >= floor``. Por defecto hoy,
      para nunca tocar slots pasados.

    Un slot "tiene reserva" si existe algún ``Appointment`` activo apuntándolo.
    Esos slots no se borran y se devuelven en ``protected``.

    Devuelve ``(cancelled, protected)`` donde ``cancelled`` es la cantidad de
    slots soft-deleteados y ``protected`` una lista de
    ``{"date", "slot", "reason": "tiene_reservas"}``.
    """
    from apps.appointments.models import Appointment

    dates = {d for d in dates if d >= (floor or date.today())}
    if not dates:
        return 0, []

    cancelled = 0
    protected = []
    with transaction.atomic():
        slots = list(Slot.objects.filter(date__in=dates).order_by('date', 'start_time'))
        # Una sola query para saber qué slots tienen reserva activa (evita N+1).
        reserved_ids = set(
            Appointment.objects.filter(slot__in=slots).values_list('slot_id', flat=True)
        )
        for slot in slots:
            if slot.id in reserved_ids:
                protected.append({
                    'date': slot.date.isoformat(),
                    'slot': slot.id,
                    'reason': 'tiene_reservas',
                })
                continue
            slot.delete()
            cancelled += 1
    return cancelled, protected


def regenerate_slots_on_dates(dates, floor=None):
    """Regenera los slots faltantes en ``dates`` según los ``SlotTemplate`` activos.

    Para cada fecha (``>= floor`` y que NO sea feriado) crea, por cada template
    activo cuyo día de semana coincida, el slot faltante (evitando duplicados de
    fecha+hora+sala vía ``all_objects``) y reserva forward los ``FixedSlot`` que
    cubran la fecha. Se usa al ACORTAR un feriado, para que las fechas que dejan de
    ser feriado no queden sin slots. Devuelve la cantidad de slots creados.
    """
    from apps.holidays.services import holiday_dates_in_range
    from .models import SlotTemplate

    target = sorted(d for d in dates if d >= (floor or date.today()))
    if not target:
        return 0

    still_holiday = holiday_dates_in_range(target[0], target[-1])
    templates = list(SlotTemplate.objects.filter(is_active=True))
    template_days = {t.id: set(t.days_of_week.values_list('day', flat=True)) for t in templates}
    fixed_by_template = {}
    for fs in FixedSlot.objects.all():
        fixed_by_template.setdefault(fs.template_id, []).append(fs)

    created = 0
    with transaction.atomic():
        for d in target:
            if d in still_holiday:
                continue
            day_name = WEEKDAY_NAMES[d.weekday()]
            for t in templates:
                if day_name not in template_days[t.id]:
                    continue
                exists = Slot.all_objects.filter(
                    date=d, start_time=t.start_time, room=t.room,
                ).exists()
                if exists:
                    continue
                new_slot = Slot.objects.create(
                    template=t, date=d,
                    start_time=t.start_time, end_time=t.end_time,
                    room=t.room, activity_subtype=t.activity_subtype,
                    availability=t.availability, status_id=1,
                )
                created += 1
                for fs in fixed_by_template.get(t.id, []):
                    if fs.covers(d):
                        reserve_person_in_slot(fs.person, new_slot, fs)
    return created


def generate_slots_for_template(template, date_from, date_to, *, user=None):
    """Genera Slots para `template` en el rango [date_from, date_to] (inclusive).

    Idempotente: saltea (fecha, hora, sala) ya existentes. Omite feriados del rango
    (y cancela los slots sin reserva que caigan en ellos, protegiendo los reservados),
    reserva forward los FixedSlot activos del template, y registra audit (Action) si
    hubo reservas automáticas o cancelaciones. Devuelve un dict resumen.

    Lógica compartida por el endpoint /generate-slots/ y el command generate_slots.
    No valida template_id, is_active, formato/ventana de fechas ni capacidad: eso lo
    hace el llamador."""
    from apps.holidays.services import holiday_dates_in_range
    from apps.actions.models import Action

    template_day_names = set(template.days_of_week.values_list('day', flat=True))
    active_fixed_slots = list(FixedSlot.objects.filter(template=template))

    holiday_dates = holiday_dates_in_range(date_from, date_to)
    slots_cancelados, slots_protegidos = cancel_unreserved_slots_on_dates(holiday_dates)

    created = skipped = feriados_omitidos = reservas_auto = 0
    warnings_forward = []
    current = date_from
    one_day = timedelta(days=1)

    while current <= date_to:
        day_name = WEEKDAY_NAMES[current.weekday()]
        if day_name in template_day_names:
            if current in holiday_dates:
                feriados_omitidos += 1
                current += one_day
                continue

            exists = Slot.all_objects.filter(
                date=current, start_time=template.start_time, room=template.room,
            ).exists()

            if exists:
                skipped += 1
            else:
                new_slot = Slot.objects.create(
                    template=template, date=current,
                    start_time=template.start_time, end_time=template.end_time,
                    room=template.room, activity_subtype=template.activity_subtype,
                    availability=template.availability, status_id=1,
                )
                created += 1
                for fs in active_fixed_slots:
                    if fs.covers(current):
                        estado = reserve_person_in_slot(fs.person, new_slot, fs)
                        if estado == "creado":
                            reservas_auto += 1
                        else:  # "slot_lleno" o "ya_reservado"
                            warnings_forward.append({
                                "date": current.isoformat(), "slot": new_slot.id,
                                "person": fs.person_id, "reason": estado,
                            })
        current += one_day

    if warnings_forward:
        logger.warning(
            "generate-slots: %d reservas forward no realizadas: %s",
            len(warnings_forward), warnings_forward,
        )

    if reservas_auto > 0:
        Action.objects.create(
            user=user, action="Crear",
            target="Reservas automáticas (generación)", target_id=template.id,
            new_value=[
                {"field": "Template", "value": f"{template}"},
                {"field": "Rango", "value": f"{date_from} a {date_to}"},
                {"field": "Reservas automáticas", "value": str(reservas_auto)},
                {"field": "Advertencias", "value": str(len(warnings_forward))},
            ],
        )

    if slots_cancelados > 0:
        Action.objects.create(
            user=user, action="Eliminar",
            target="Slots cancelados por feriado (generación)", target_id=template.id,
            new_value=[
                {"field": "Template", "value": f"{template}"},
                {"field": "Rango", "value": f"{date_from} a {date_to}"},
                {"field": "Slots cancelados", "value": str(slots_cancelados)},
                {"field": "Slots protegidos", "value": str(len(slots_protegidos))},
            ],
        )

    return {
        "created": created,
        "skipped": skipped,
        "feriados_omitidos": feriados_omitidos,
        "reservas_automaticas": reservas_auto,
        "warnings": warnings_forward,
        "slots_cancelados": slots_cancelados,
        "slots_protegidos": slots_protegidos,
    }
