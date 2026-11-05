"""Bloqueo temporal de autenticación (cuenta + IP), persistido en PostgreSQL.

Por qué en la base de datos: no hay Redis y la caché por defecto (LocMem) no se
comparte entre los workers de gunicorn, así que los contadores en caché serían
eludibles. La DB ya existe, es compartida por todos los workers y el bloqueo
sobrevive a reinicios.

Reglas (configurables en settings):
- Cuenta: AUTH_LOCKOUT_MAX_FAILURES (5) fallos en AUTH_LOCKOUT_WINDOW (15 min)
  -> bloqueo de AUTH_LOCKOUT_DURATION (15 min). La clave es la cuenta resuelta,
  así que email y DNI comparten contador, y todos los endpoints de autenticación
  (/login/, /student-login/, /token/, /api-auth/ y la verificación de contraseña
  actual) usan el mismo servicio. Identificadores inexistentes se cuentan y
  bloquean igual (misma respuesta: no revela si la cuenta existe).
- IP: AUTH_IP_MAX_FAILURES (20) fallos en la ventana -> bloqueo de la IP en
  todos los endpoints de autenticación. Limita cuántas cuentas ajenas puede
  bloquear un mismo origen y frena el "password spraying" desde una IP.
- Endpoints públicos sensibles (registro, recuperación): AUTH_IP_MAX_REQUESTS
  (30) peticiones por IP en la ventana.
"""
import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import AuthFailure, AuthLock
from .net import client_ip

logger = logging.getLogger("security.auth")

GENERIC_LOCK_MSG = "Demasiados intentos fallidos. Esperá unos minutos e intentá de nuevo."


def _cfg(name, default):
    return getattr(settings, name, default)


def max_failures():
    return _cfg("AUTH_LOCKOUT_MAX_FAILURES", 5)


def window():
    return _cfg("AUTH_LOCKOUT_WINDOW", timedelta(minutes=15))


def duration():
    return _cfg("AUTH_LOCKOUT_DURATION", timedelta(minutes=15))


def ip_max_failures():
    return _cfg("AUTH_IP_MAX_FAILURES", 20)


def ip_max_requests():
    return _cfg("AUTH_IP_MAX_REQUESTS", 30)


class AuthLocked(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = GENERIC_LOCK_MSG
    default_code = "auth_locked"

    def __init__(self, retry_after=None):
        super().__init__()
        self.wait = int(retry_after.total_seconds()) + 1 if retry_after else None


def normalize_identifier(identifier):
    return (identifier or "").strip().lower()


def account_key(identifier):
    """Misma clave para email y DNI de una cuenta. Si no existe, hash del
    identificador normalizado (no se guarda el dato en claro)."""
    from .models import CustomUser
    ident = normalize_identifier(identifier)
    if not ident:
        return None
    user = CustomUser.all_objects.filter(Q(email__iexact=ident) | Q(dni=ident)).only("pk").first()
    if user is not None:
        return f"user:{user.pk}"
    return "ident:" + hashlib.sha256(ident.encode()).hexdigest()[:40]


def user_key(user):
    return f"user:{user.pk}"


def _ip_key(request):
    return client_ip(request) if request is not None else None


def _active_lock(scope, key, now):
    if not key:
        return None
    lock = AuthLock.objects.filter(scope=scope, key=key, locked_until__gt=now).first()
    return lock


def check(request=None, acct_key=None):
    """Lanza AuthLocked si la IP o la cuenta están bloqueadas."""
    now = timezone.now()
    for scope, key in (("ip", _ip_key(request)), ("account", acct_key)):
        lock = _active_lock(scope, key, now)
        if lock is not None:
            raise AuthLocked(retry_after=lock.locked_until - now)


def _count_and_maybe_lock(scope, key, limit, now):
    lock = AuthLock.objects.filter(scope=scope, key=key).first()
    since = now - window()
    if lock is not None:
        lock_start = lock.locked_until - duration()
        if lock_start > since:
            since = lock_start
    n = AuthFailure.objects.filter(scope=scope, key=key, created_at__gt=since).count()
    if n >= limit:
        AuthLock.objects.update_or_create(scope=scope, key=key, defaults={"locked_until": now + duration()})
        logger.warning("auth lock: scope=%s key=%s failures=%s", scope, key, n)
        return True
    return False


def register_failure(request=None, acct_key=None):
    now = timezone.now()
    ip = _ip_key(request)
    rows = []
    if acct_key:
        rows.append(AuthFailure(scope="account", key=acct_key, created_at=now))
    if ip:
        rows.append(AuthFailure(scope="ip", key=ip, created_at=now))
    AuthFailure.objects.bulk_create(rows)
    # Limpieza oportunista de registros viejos.
    AuthFailure.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
    if acct_key:
        _count_and_maybe_lock("account", acct_key, max_failures(), now)
    if ip:
        _count_and_maybe_lock("ip", ip, ip_max_failures(), now)


def register_success(acct_key):
    """Login correcto: se reinicia el contador de la cuenta (no el de la IP)."""
    if acct_key:
        AuthFailure.objects.filter(scope="account", key=acct_key).delete()


def clear_account(user):
    """Desbloqueo explícito (recuperación de contraseña exitosa, comando admin)."""
    key = user_key(user)
    AuthFailure.objects.filter(scope="account", key=key).delete()
    AuthLock.objects.filter(scope="account", key=key).delete()


def count_request(request):
    """Presupuesto por IP para endpoints públicos sensibles (registro,
    recuperación). Lanza AuthLocked al superarlo."""
    ip = _ip_key(request)
    if not ip:
        return
    now = timezone.now()
    check(request)
    lock = _active_lock("ip_req", ip, now)
    if lock is not None:
        raise AuthLocked(retry_after=lock.locked_until - now)
    AuthFailure.objects.create(scope="ip_req", key=ip, created_at=now)
    if _count_and_maybe_lock("ip_req", ip, ip_max_requests() + 1, now):
        raise AuthLocked(retry_after=duration())
