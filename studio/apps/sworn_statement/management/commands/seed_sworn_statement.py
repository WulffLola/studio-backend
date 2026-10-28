"""
Seed de la declaración jurada inicial del estudio.

Crea una SwornStatement si no existe ninguna activa.
Si ya hay una, no hace nada (idempotente).

Uso:
    python manage.py seed_sworn_statement
    python manage.py seed_sworn_statement --force   # reemplaza la existente
"""

from django.core.management.base import BaseCommand
from apps.sworn_statement.models import SwornStatement

TEXT = """\
DECLARACIÓN JURADA

Yo, el/la abajo firmante, declaro bajo juramento que:

1. Me encuentro en condiciones físicas aptas para realizar actividades físicas y/o artísticas.
2. No padezco ninguna enfermedad, lesión o condición médica que me impida participar \
en las actividades ofrecidas por el estudio.
3. En caso de poseer alguna condición médica relevante, me comprometo a informarla \
al estudio antes de iniciar cualquier actividad.
4. Eximo al estudio y a sus docentes de toda responsabilidad por lesiones o daños \
derivados de la omisión de información médica relevante.
5. Acepto y conozco el reglamento interno del estudio.

El presente documento tiene carácter de declaración jurada y es condición para \
inscribirse y participar en las actividades del estudio.
"""


class Command(BaseCommand):
    help = 'Crea la declaración jurada inicial del estudio (idempotente).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Crea una nueva versión aunque ya exista una activa.',
        )

    def handle(self, *args, **options):
        existing = SwornStatement.objects.first()

        if existing and not options['force']:
            self.stdout.write(self.style.WARNING(
                f'Ya existe una declaración jurada activa (id={existing.id}). '
                'Usá --force para crear una nueva versión.'
            ))
            return

        statement = SwornStatement.objects.create(text=TEXT)
        self.stdout.write(self.style.SUCCESS(
            f'Declaración jurada creada (id={statement.id}).'
        ))
