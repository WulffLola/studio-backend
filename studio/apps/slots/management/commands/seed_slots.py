"""
Seed de slots para pruebas del frontend.

Crea 10 SlotTemplates con distintas combinaciones de días/horarios y genera
las occurrences concretas (Slot) para un rango de 6 semanas a partir de hoy.

Uso:
    python manage.py seed_slots
    python manage.py seed_slots --weeks 8        # rango personalizado
    python manage.py seed_slots --from 2026-04-01 --to 2026-04-30
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.activity_subtype.models import ActivitySubType
from apps.rooms.models import Room
from apps.slots.models import Slot, SlotTemplate
from apps.weeks.models import Week


# ---------------------------------------------------------------------------
# Definición de templates
# ---------------------------------------------------------------------------
#
# days: lista de ids de Week  (1=Lun … 7=Dom)
# room: id de Room  (se usa el primero disponible si no existe)
# activity_subtype: id de ActivitySubType (igual)
#
TEMPLATES = [
    # Diario (Lun–Vie)
    {
        "label": "Diario mañana · 07:00–08:00",
        "days": [1, 2, 3, 4, 5],
        "start": "07:00", "end": "08:00",
        "room": 1, "activity_subtype": 1,
        "availability": 12,
    },
    {
        "label": "Diario tarde · 18:00–19:00",
        "days": [1, 2, 3, 4, 5],
        "start": "18:00", "end": "19:00",
        "room": 1, "activity_subtype": 1,
        "availability": 12,
    },
    {
        "label": "Diario noche · 20:00–21:00",
        "days": [1, 2, 3, 4, 5],
        "start": "20:00", "end": "21:00",
        "room": 2, "activity_subtype": 2,
        "availability": 10,
    },
    # Lunes, Miércoles, Viernes
    {
        "label": "LMV mañana · 08:00–09:00",
        "days": [1, 3, 5],
        "start": "08:00", "end": "09:00",
        "room": 1, "activity_subtype": 1,
        "availability": 10,
    },
    {
        "label": "LMV mediodía · 12:00–13:00",
        "days": [1, 3, 5],
        "start": "12:00", "end": "13:00",
        "room": 2, "activity_subtype": 2,
        "availability": 8,
    },
    {
        "label": "LMV tarde · 17:00–18:00",
        "days": [1, 3, 5],
        "start": "17:00", "end": "18:00",
        "room": 1, "activity_subtype": 1,
        "availability": 10,
    },
    # Martes y Jueves
    {
        "label": "Mar-Jue mañana · 09:00–10:00",
        "days": [2, 4],
        "start": "09:00", "end": "10:00",
        "room": 2, "activity_subtype": 2,
        "availability": 8,
    },
    {
        "label": "Mar-Jue noche · 19:00–20:00",
        "days": [2, 4],
        "start": "19:00", "end": "20:00",
        "room": 1, "activity_subtype": 1,
        "availability": 10,
    },
    # Sábado
    {
        "label": "Sábado mañana · 09:00–10:30",
        "days": [6],
        "start": "09:00", "end": "10:30",
        "room": 1, "activity_subtype": 1,
        "availability": 15,
    },
    # Fin de semana
    {
        "label": "Sáb-Dom tarde · 16:00–17:00",
        "days": [6, 7],
        "start": "16:00", "end": "17:00",
        "room": 2, "activity_subtype": 2,
        "availability": 12,
    },
]


class Command(BaseCommand):
    help = "Crea SlotTemplates y genera Slots concretos para pruebas."

    def add_arguments(self, parser):
        parser.add_argument("--weeks", type=int, default=6,
                            help="Semanas a generar desde hoy (default: 6)")
        parser.add_argument("--from", dest="date_from", default=None,
                            help="Fecha de inicio YYYY-MM-DD (override --weeks)")
        parser.add_argument("--to", dest="date_to", default=None,
                            help="Fecha de fin YYYY-MM-DD (override --weeks)")

    def handle(self, *args, **options):
        date_from, date_to = self._resolve_range(options)

        self.stdout.write(f"Rango: {date_from} → {date_to}\n")

        # Fallbacks: si no hay rooms/activity_subtypes, los crea mínimos
        room1 = self._get_or_warn(Room, 1, "Room")
        room2 = self._get_or_warn(Room, 2, "Room")
        act1  = self._get_or_warn(ActivitySubType, 1, "ActivitySubType")
        act2  = self._get_or_warn(ActivitySubType, 2, "ActivitySubType")

        room_map = {1: room1, 2: room2}
        act_map  = {1: act1,  2: act2}

        total_created = 0

        for cfg in TEMPLATES:
            template = self._get_or_create_template(cfg, room_map, act_map)
            if template is None:
                continue

            created, skipped = self._generate_slots(template, date_from, date_to)
            total_created += created

            self.stdout.write(
                self.style.SUCCESS(
                    f"  [{cfg['label']}]  → {created} slots nuevos, {skipped} omitidos"
                )
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal: {total_created} slots creados."
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_range(self, options):
        if options["date_from"] and options["date_to"]:
            return date.fromisoformat(options["date_from"]), date.fromisoformat(options["date_to"])
        today = date.today()
        return today, today + timedelta(weeks=options["weeks"])

    def _get_or_warn(self, model, pk, label):
        try:
            return model.objects.get(pk=pk)
        except model.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"  {label} id={pk} no existe — algunos templates se omitirán."
            ))
            return None

    def _get_or_create_template(self, cfg, room_map, act_map):
        room = room_map.get(cfg["room"])
        act  = act_map.get(cfg["activity_subtype"])

        # Buscar template existente por horario + sala + actividad
        qs = SlotTemplate.objects.filter(
            start_time=cfg["start"],
            end_time=cfg["end"],
            room=room,
            activity_subtype=act,
        )
        if qs.exists():
            return qs.first()

        template = SlotTemplate.objects.create(
            start_time=cfg["start"],
            end_time=cfg["end"],
            room=room,
            activity_subtype=act,
            availability=cfg["availability"],
        )
        week_objs = Week.objects.filter(id__in=cfg["days"])
        template.days_of_week.set(week_objs)
        return template

    def _generate_slots(self, template, date_from, date_to):
        from apps.holidays.services import holiday_dates_in_range

        template_week_ids = set(template.days_of_week.values_list("id", flat=True))
        holiday_dates = holiday_dates_in_range(date_from, date_to)  #
        created = skipped = 0
        current = date_from

        while current <= date_to:
            week_id = current.weekday() + 1  # 1=Lun … 7=Dom

            if week_id in template_week_ids and current not in holiday_dates:
                exists = Slot.all_objects.filter(
                    template=template,
                    date=current,
                    start_time=template.start_time,
                ).exists()

                if exists:
                    skipped += 1
                else:
                    Slot.objects.create(
                        template=template,
                        date=current,
                        start_time=template.start_time,
                        end_time=template.end_time,
                        room=template.room,
                        activity_subtype=template.activity_subtype,
                        availability=template.availability,
                        status_id=1,
                    )
                    created += 1

            current += timedelta(days=1)

        return created, skipped
