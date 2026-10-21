import os
import requests
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from apps.people.models import Person


class Command(BaseCommand):
    help = 'Envía un recordatorio a las personas cuya cobertura (prueba o plan) vence en 3 días.'

    def handle(self, *args, **kwargs):
        target_date = timezone.now().date() + timedelta(days=3)

        candidates = Person.objects.filter(deleted__isnull=True).filter(
            Q(exp_date=target_date) | Q(active_plans__exp_date=target_date)
        ).distinct()

        message_url = os.getenv("API_WPP_SEND_MESSAGE")
        notified_any = False

        for person in candidates:
            coverage_end = person.latest_coverage_end()
            if coverage_end != target_date:
                # Su cobertura más reciente no vence exactamente en 3 días (tiene otra más larga).
                continue
            notified_any = True
            try:
                if person.phone:
                    # la fecha se muestra como dd/mm/yyyy (no yyyy-mm-dd).
                    # Solo formato de presentación: no altera el valor almacenado.
                    coverage_end_str = coverage_end.strftime('%d/%m/%Y')
                    message = (
                        f"Hola {person.name}, 😊 queremos recordarte que tu pago vencerá el día {coverage_end_str}. "
                        f"Si no realizas el pago antes del {coverage_end_str}, tendrás 7 días adicionales para realizarlo. "
                        "De no hacerlo, su suscripción será dada de baja automáticamente. 💔 ¡Gracias por elegirnos! 💖"
                    )
                    payload = {"number": person.phone, "message": message}
                    response = requests.post(message_url, json=payload, timeout=10)
                    response.raise_for_status()
                    self.stdout.write(self.style.SUCCESS(f"Mensaje enviado a {person.phone} para {person.name}."))
                else:
                    self.stdout.write(self.style.WARNING(f"Persona {person.name} no tiene número de teléfono registrado."))
            except requests.Timeout:
                self.stdout.write(self.style.ERROR(f"Timeout al enviar el mensaje a {person.phone}."))
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Error al enviar el mensaje a {person.phone}: {e}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error general con la persona {person.id}: {e}"))

        if notified_any:
            self.stdout.write(self.style.SUCCESS('Proceso completado.'))
        else:
            self.stdout.write(self.style.SUCCESS('No hay personas con cobertura por vencer en 3 días.'))
