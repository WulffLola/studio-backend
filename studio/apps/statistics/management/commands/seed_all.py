"""
Carga datos de prueba completos para levantar el proyecto en local.

Vacía la base y genera, con fechas alrededor de hoy:
- 2 sedes, 3 salas, plantillas de horario y clases (8 semanas atrás y 3 adelante);
- alumnos con planes, turnos fijos, reservas, lista de espera y algunas bajas;
- pagos, gastos, profesoras con sus turnos y horas, notas, recetas y publicaciones;
- un usuario por rol: super@, admin@ y recepcion@studio.local (contraseña studio1234).

Uso:
    python manage.py seed_all                 # 60 alumnos
    python manage.py seed_all --alumnos 120

Con DEBUG desactivado pide --reset para confirmar, porque borra todos los datos.
Usa el mismo generador que seed_demo (el de la demo publicada), en tamaño chico.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Vacía la base y carga datos de prueba completos (usuarios por rol, alumnos, turnos, pagos…)."

    def add_arguments(self, parser):
        parser.add_argument("--alumnos", type=int, default=60,
                            help="Cantidad de alumnos activos (60 por defecto).")
        parser.add_argument("--reset", action="store_true",
                            help="Confirma que se borran todos los datos (obligatorio con DEBUG=false).")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["reset"]:
            raise CommandError(
                "DEBUG está desactivado y este comando borra toda la base. "
                "Si es lo que querés, ejecutalo con --reset."
            )
        call_command(
            "seed_demo",
            reset=True,
            alumnos=options["alumnos"],
            usuarios_locales=True,
            stdout=self.stdout,
            stderr=self.stderr,
        )
