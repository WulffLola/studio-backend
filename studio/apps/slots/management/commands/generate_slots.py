import logging

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.slots.models import SlotTemplate
from apps.slots.services import generate_slots_for_template, capacity_exceeded_message

logger = logging.getLogger(__name__)

GENERATION_MONTHS = 3


class Command(BaseCommand):
    help = (
        "Genera slots para todos los SlotTemplate activos desde hoy hasta hoy + 3 "
        "meses. Idempotente (saltea los que ya existen). Pensado para correr por cron "
        "y mantener la ventana rolling de 3 meses sin llamar al endpoint."
    )

    def handle(self, *args, **options):
        today = timezone.localdate()
        date_to = today + relativedelta(months=GENERATION_MONTHS)

        templates = SlotTemplate.objects.filter(is_active=True)
        if not templates.exists():
            self.stdout.write(self.style.WARNING("No hay templates activos para generar."))
            return

        total_created = 0
        fallidos = 0
        for template in templates:
            # Misma validacion de capacidad que el endpoint: la sala pudo reducir su
            # capacidad despues de crear el template.
            cap_msg = capacity_exceeded_message(template.availability, template.room_id)
            if cap_msg:
                self.stderr.write(self.style.WARNING(
                    f"Template {template.id} omitido por capacidad: {cap_msg}"
                ))
                continue

            try:
                with transaction.atomic():
                    summary = generate_slots_for_template(template, today, date_to)
            except Exception:
                fallidos += 1
                logger.exception("generate_slots: fallo generando template %s", template.id)
                self.stderr.write(self.style.ERROR(
                    f"Template {template.id}: error al generar (ver logs)."
                ))
                continue

            total_created += summary["created"]
            self.stdout.write(self.style.SUCCESS(
                f"Template {template.id}: {summary['created']} creados, "
                f"{summary['skipped']} omitidos, {summary['feriados_omitidos']} por feriado."
            ))

        self.stdout.write(self.style.SUCCESS(
            f"Generacion completa ({today.isoformat()} a {date_to.isoformat()}): "
            f"{total_created} slots creados en total."
        ))

        if fallidos:
            # Exit code != 0 para que el cron alerte, sin descartar lo ya generado.
            raise CommandError(f"{fallidos} template(s) fallaron durante la generacion.")
