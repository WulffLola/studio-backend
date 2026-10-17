"""Valida (y opcionalmente corrige) la consistencia de identidad User<->Person.

Uso:
    python manage.py validate_identity_consistency          # reporta; exit 1 si hay drift
    python manage.py validate_identity_consistency --fix    # corrige desde el User (canónico)
"""
import sys

from django.core.management.base import BaseCommand

from apps.users.identity_sync import find_identity_mismatches, sync_user_to_person


class Command(BaseCommand):
    help = "Valida y opcionalmente corrige la consistencia de identidad User<->Person."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix', action='store_true',
            help='Corrige las divergencias desde el lado canónico (User).',
        )

    def handle(self, *args, **options):
        mismatches = find_identity_mismatches()

        if not mismatches:
            self.stdout.write(self.style.SUCCESS("Sin divergencias de identidad."))
            return

        for user, person, fields in mismatches:
            self.stdout.write(
                f"User #{user.pk} <-> Person #{person.pk}: {', '.join(fields)}"
            )

        if options['fix']:
            for user, person, _fields in mismatches:
                sync_user_to_person(user)
            self.stdout.write(self.style.SUCCESS(f"Corregidos {len(mismatches)} par(es)."))
        else:
            sys.exit(1)
