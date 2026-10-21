import os
import requests
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.people.models import Person
from apps.appointments.models import Appointment


class Command(BaseCommand):
    help = ('Da de baja a las personas cuya cobertura (turnos de prueba o planes pagos) '
            'venció hace 7 días, elimina sus citas y envía un aviso.')

    def handle(self, *args, **kwargs):
        limit_date = timezone.now().date() - timedelta(days=7)

        # Candidatos: personas con alguna fecha de cobertura vencida (prueba o plan).
        # El corte final por persona lo decide latest_coverage_end() (el máximo entre
        # ambas fuentes), para no dar de baja a quien todavía tiene otra cobertura vigente.
        candidates = Person.objects.filter(deleted__isnull=True).filter(
            Q(exp_date__lte=limit_date) | Q(active_plans__exp_date__lte=limit_date)
        ).distinct()

        message_url = os.getenv("API_WPP_SEND_MESSAGE")
        removed_any = False

        for person in candidates:
            coverage_end = person.latest_coverage_end()
            if coverage_end is None or coverage_end > limit_date:
                # Sigue dentro de la ventana de gracia por otra cobertura -> no se da de baja.
                continue
            removed_any = True
            try:
                with transaction.atomic():
                    was_payer = person.active_plans.exists()

                    # Eliminar citas asociadas y liberar sus slots.
                    appointments = Appointment.objects.filter(person=person, deleted__isnull=True)
                    for appointment in appointments:
                        slot = appointment.slot
                        if slot:
                            slot.availability = (slot.availability or 0) + 1
                            if slot.availability > 0 and slot.status and slot.status.id == 2:
                                slot.status_id = 1
                            slot.save()
                        appointment.deleted = timezone.now()
                        appointment.save()

                    # Soft-delete de sus planes activos (para que no queden como fantasmas
                    # en overdue-payments) y baja de la persona.
                    person.active_plans.update(deleted=timezone.now().date())
                    person.deleted = timezone.now()
                    person.exp_date = None
                    person.save()

                # Mensaje según si era pagante o de prueba.
                if person.phone:
                    if was_payer:
                        message = (
                            f"Hola {person.name}, 💔 lamentamos informarte que tus servicios han sido dados de baja "
                            "automáticamente por falta de pago. Si deseas reactivarlos, por favor comunícate con nosotros. "
                            "¡Gracias! 😊"
                        )
                    else:
                        message = (
                            f"Hola {person.name}, lamentamos informarte que tus turnos de prueba han sido eliminados debido a que no se registró "
                            "un pago a tiempo. Si deseas continuar usando nuestros servicios, por favor comunícate con nosotros. ¡Gracias! 😊"
                        )
                    payload = {"number": person.phone, "message": message}
                    response = requests.post(message_url, json=payload, timeout=10)
                    response.raise_for_status()
                    self.stdout.write(self.style.SUCCESS(f"Mensaje enviado a {person.phone} para {person.name}."))
                else:
                    self.stdout.write(self.style.WARNING(f"Persona {person.name} no tiene número de teléfono registrado."))

                self.stdout.write(self.style.SUCCESS(f"Persona {person.id} y sus citas han sido eliminadas."))

            except requests.Timeout:
                self.stdout.write(self.style.ERROR(f"Timeout al enviar el mensaje a {person.phone}."))
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Error al enviar el mensaje a {person.phone}: {e}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error general con la persona {person.id}: {e}"))

        if removed_any:
            self.stdout.write(self.style.SUCCESS('Proceso completado.'))
        else:
            self.stdout.write(self.style.SUCCESS('No hay personas con cobertura vencida por 7 días.'))
