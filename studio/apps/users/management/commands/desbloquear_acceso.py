from django.core.management.base import BaseCommand, CommandError

from apps.users import lockout
from apps.users.models import AuthFailure, AuthLock


class Command(BaseCommand):
    help = "Quita el bloqueo temporal de login de una cuenta (email o DNI) o de una IP."

    def add_arguments(self, parser):
        parser.add_argument("valor", help="email, DNI o IP")
        parser.add_argument("--ip", action="store_true", help="el valor es una IP")

    def handle(self, valor, ip=False, **opts):
        if ip:
            scopes, key = ("ip", "ip_req"), valor
        else:
            key = lockout.account_key(valor)
            if key is None:
                raise CommandError("Valor vacío")
            scopes = ("account",)
        n_locks = AuthLock.objects.filter(scope__in=scopes, key=key).delete()[0]
        n_fail = AuthFailure.objects.filter(scope__in=scopes, key=key).delete()[0]
        self.stdout.write(f"Desbloqueado {key}: {n_locks} bloqueo(s), {n_fail} intento(s) borrados.")
