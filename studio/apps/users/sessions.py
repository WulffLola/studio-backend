"""Sesiones JWT con control del lado servidor.

Política (valores en settings):
- access: SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] (20 min)
- refresh: rotación + blacklist; nunca vence después del máximo de la sesión
- máximo absoluto: AUTH_SESSION_MAX_AGE (8 h desde el login, aunque se renueve)
- inactividad: AUTH_SESSION_IDLE_TIMEOUT (30 min sin actividad real del usuario)
- revocación inmediata: por sesión (AuthSession.revoked_at) o global
  (CustomUser.token_version)

Actividad real: el frontend envía en cada petición el header ``X-Client-Idle``
con los segundos transcurridos desde la última interacción del usuario
(teclado, mouse, toque). El backend toma como última actividad
``ahora - X-Client-Idle``, así que el polling o las peticiones automáticas de una
pestaña inactiva no extienden la sesión. El refresh nunca cuenta como actividad.
Las peticiones sin el header (requests manuales, polling, otros clientes) NO
cuentan como actividad (AUTH_ACTIVITY_HEADER_REQUIRED=True por defecto).
La caducidad siempre la decide el servidor con su propio last_activity_at.
"""
import math
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuthSession
from .net import client_ip

ACTIVITY_HEADER = "HTTP_X_CLIENT_IDLE"
# Para no escribir en la DB en cada request: solo se actualiza la última
# actividad si avanzó al menos esto.
ACTIVITY_WRITE_GRANULARITY = timedelta(seconds=30)
# Un idle mayor ya implica sesión vencida; valores más grandes se descartan.
MAX_REPORTED_IDLE_SECONDS = 24 * 3600


def max_age():
    return getattr(settings, "AUTH_SESSION_MAX_AGE", timedelta(hours=8))


def idle_timeout():
    return getattr(settings, "AUTH_SESSION_IDLE_TIMEOUT", timedelta(minutes=30))


class SessionInvalid(AuthenticationFailed):
    default_detail = "La sesión no es válida. Iniciá sesión nuevamente."
    default_code = "session_invalid"


def _fail(detail, code):
    raise SessionInvalid(detail=detail, code=code)


def _ts(dt):
    return int(dt.timestamp())


def _cap_exp(token, session):
    """Ningún token puede vencer después del máximo absoluto de la sesión."""
    limit = _ts(session.expires_at)
    if int(token.payload.get("exp", limit)) > limit:
        token.payload["exp"] = limit


def _bind(refresh, session, user):
    refresh["sid"] = str(session.id)
    refresh["tv"] = user.token_version
    _cap_exp(refresh, session)


def token_pair(refresh, session):
    access = refresh.access_token  # copia sid/tv (no copia exp/jti/iat)
    _cap_exp(access, session)
    return {
        "refresh": str(refresh),
        "access": str(access),
        "session_expires_at": session.expires_at.isoformat(),
    }


def issue_tokens(user, request=None):
    """Crea una AuthSession y devuelve el par de tokens ligado a ella."""
    now = timezone.now()
    session = AuthSession.objects.create(
        user=user,
        created_at=now,
        last_activity_at=now,
        expires_at=now + max_age(),
        ip=client_ip(request) if request is not None else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:255],
    )
    refresh = RefreshToken.for_user(user)
    _bind(refresh, session, user)
    update_last_login(None, user)
    return token_pair(refresh, session), session


def revoke_session(session, reason):
    if session.revoked_at is None:
        AuthSession.objects.filter(pk=session.pk, revoked_at__isnull=True).update(
            revoked_at=timezone.now(), revoke_reason=reason[:30]
        )
        session.revoked_at = timezone.now()
        session.revoke_reason = reason[:30]


def revoke_all_sessions(user, reason, except_session_id=None, bump_version=True):
    """Revoca todas las sesiones del usuario. Con bump_version también invalida
    cualquier token emitido (incluidos los que no tengan sesión asociada)."""
    qs = AuthSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_session_id is not None:
        qs = qs.exclude(pk=except_session_id)
    qs.update(revoked_at=timezone.now(), revoke_reason=reason[:30])
    if bump_version:
        from django.db.models import F
        type(user).all_objects.filter(pk=user.pk).update(token_version=F("token_version") + 1)
        user.refresh_from_db(fields=["token_version"])
    # Refresh tokens pendientes a la blacklist (defensa adicional).
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        if except_session_id is None:
            for tok in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
                BlacklistedToken.objects.get_or_create(token=tok)
    except Exception:  # pragma: no cover - la app de blacklist está instalada
        pass


def validate_session(payload, user):
    """Valida que el token pertenezca a una sesión viva. Devuelve la AuthSession."""
    sid = payload.get("sid")
    if not sid:
        _fail("Token sin sesión asociada. Iniciá sesión nuevamente.", "session_missing")
    if int(payload.get("tv", -1)) != user.token_version:
        _fail("La sesión fue revocada. Iniciá sesión nuevamente.", "session_revoked")
    session = AuthSession.objects.filter(pk=sid, user_id=user.pk).first()
    if session is None or session.revoked_at is not None:
        _fail("La sesión fue revocada. Iniciá sesión nuevamente.", "session_revoked")
    now = timezone.now()
    if now >= session.expires_at:
        revoke_session(session, "max_age")
        _fail("La sesión alcanzó su duración máxima. Iniciá sesión nuevamente.", "session_expired")
    if now - session.last_activity_at > idle_timeout():
        revoke_session(session, "idle")
        _fail("La sesión expiró por inactividad. Iniciá sesión nuevamente.", "session_idle")
    return session


def reported_activity_at(request, now=None):
    """Momento de la última actividad real informada por el cliente, o None si
    la petición no debe contar como actividad.

    El valor del cliente nunca decide por sí solo: la caducidad la controla
    validate_session() con el last_activity_at guardado en el servidor ANTES de
    mirar este header, y el header solo puede mover la actividad hacia adelante
    hasta "ahora" (nunca al futuro). Sin header válido no hay crédito de
    actividad (polling, requests manuales, refresh).
    """
    now = now or timezone.now()
    raw = request.META.get(ACTIVITY_HEADER)
    if raw is None or str(raw).strip() == "":
        if getattr(settings, "AUTH_ACTIVITY_HEADER_REQUIRED", True):
            return None
        return now
    try:
        idle = float(raw)
    except (TypeError, ValueError):
        return None
    # negativo, NaN, infinito o absurdo -> no cuenta (y nunca provoca un 500)
    if not math.isfinite(idle) or idle < 0 or idle > MAX_REPORTED_IDLE_SECONDS:
        return None
    return now - timedelta(seconds=idle)


def touch_session(session, request):
    activity = reported_activity_at(request)
    if activity is None:
        return
    if activity - session.last_activity_at >= ACTIVITY_WRITE_GRANULARITY:
        AuthSession.objects.filter(pk=session.pk, last_activity_at__lt=activity).update(
            last_activity_at=activity
        )
        session.last_activity_at = activity
