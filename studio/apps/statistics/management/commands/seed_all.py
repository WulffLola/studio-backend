"""
Pobla la base de datos completa para testing con un solo comando.

Carga los fixtures JSON en orden de dependencia y luego ejecuta
los comandos de seed individuales.

Uso:
    python manage.py seed_all
    python manage.py seed_all --skip-fixtures   # solo los comandos seed_*
    python manage.py seed_all --skip-commands   # solo los fixtures JSON
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


# Fixtures en orden de dependencia (FK primero)
FIXTURES = [
    'data_seed/001_user_type.json',
    'data_seed/002_users.seed.json',
    'data_seed/003_activity_type.seed.json',
    'data_seed/004_expense_type.seed.json',
    'data_seed/007_plans_seed.json',
    'data_seed/008_plans_type.seed.json',
    'data_seed/009_recipes.seed.json',
    'data_seed/010_status.seed.json',
    'data_seed/011_studio.seed.json',
    'data_seed/012_teacher_rol.seed.json',
    'data_seed/013_teachers.seed.json',
    'data_seed/014_weeks.seed.json',
    'data_seed/015_activity_subtype.seed.json',
    'data_seed/017_payment_method.seed.json',
    'data_seed/018_people.seed.json',
    'data_seed/019_plans_subtype.seed.json',
    'data_seed/020_room.seed.json',
    'data_seed/005_holidays.seed.json',
    'data_seed/006_notes.seed.json',
    'data_seed/016_expenses.seed.json',
    'data_seed/021_teachers_hours.seed.json',
    'data_seed/022_actions.seed.json',
    'data_seed/023_slots.seed.json',
    'data_seed/024_payments.seed.json',
    'data_seed/029_person_active_plans.seed.json',
    'data_seed/025_teachers_turn.seed.json',
    'data_seed/026_appointments.seed.json',
    'data_seed/027_extra_hours.seed.json',
    'data_seed/028_waiting_list.seed.json',
]

# Comandos seed individuales (se ejecutan después de los fixtures)
SEED_COMMANDS = [
    ('seed_students', {}),
    ('seed_slots', {}),
    ('seed_sworn_statement', {}),
]


class Command(BaseCommand):
    help = 'Pobla la base de datos completa para testing (fixtures + seeds).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-fixtures',
            action='store_true',
            help='Omite la carga de archivos JSON y solo ejecuta los seed_* commands.',
        )
        parser.add_argument(
            '--skip-commands',
            action='store_true',
            help='Omite los seed_* commands y solo carga los fixtures JSON.',
        )

    def handle(self, *args, **options):
        if not options['skip_fixtures']:
            self._load_fixtures()

        if not options['skip_commands']:
            self._run_seed_commands()

        self.stdout.write(self.style.SUCCESS('\n✓ Base de datos poblada correctamente.'))

    def _load_fixtures(self):
        self.stdout.write(self.style.HTTP_INFO('\n── Cargando fixtures ──────────────────'))
        for fixture in FIXTURES:
            try:
                call_command('loaddata', fixture, verbosity=0)
                self.stdout.write(self.style.SUCCESS(f'  ✓ {fixture}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ {fixture}: {e}'))

    def _run_seed_commands(self):
        self.stdout.write(self.style.HTTP_INFO('\n── Ejecutando seed commands ───────────'))
        for command, kwargs in SEED_COMMANDS:
            try:
                call_command(command, **kwargs, verbosity=0)
                self.stdout.write(self.style.SUCCESS(f'  ✓ {command}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ {command}: {e}'))
