from rest_framework_simplejwt.authentication import JWTAuthentication

from .sessions import touch_session, validate_session


class SessionJWTAuthentication(JWTAuthentication):
    """JWTAuthentication + validación de la AuthSession del token (revocación,
    máximo de 8 h, inactividad de 30 min) y registro de actividad real."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        session = validate_session(token.payload, user)
        touch_session(session, request)
        user._auth_session = session
        return user, token


# ---------------------------------------------------------------------------
# Sesiones por cookie de Django (/api-auth/, browsable API, Swagger).
# Aplican las mismas reglas que las sesiones JWT: máximo absoluto de 8 h e
# inactividad de 30 min controlados en el servidor, con el mismo criterio de
# actividad real (header X-Client-Idle). Sin esto, una cookie de sesión
# salteaba los límites.
# ---------------------------------------------------------------------------
from django.contrib.auth import logout as django_logout
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication

from .sessions import SessionInvalid, idle_timeout, max_age, reported_activity_at

SESSION_STARTED_KEY = "_auth_started_at"
SESSION_ACTIVITY_KEY = "_auth_last_activity_at"


def stamp_cookie_session(sender, request, user, **kwargs):
    """Receptor de user_logged_in: marca inicio y actividad de la sesión."""
    if request is not None and hasattr(request, "session"):
        now = timezone.now().timestamp()
        request.session[SESSION_STARTED_KEY] = now
        request.session[SESSION_ACTIVITY_KEY] = now


class IdleSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        django_request = request._request
        session = django_request.session
        now = timezone.now()
        started = session.get(SESSION_STARTED_KEY)
        last = session.get(SESSION_ACTIVITY_KEY)
        expired = (
            started is None or last is None
            or now.timestamp() - started >= max_age().total_seconds()
            or now.timestamp() - last > idle_timeout().total_seconds()
        )
        if expired:
            django_logout(django_request)
            raise SessionInvalid("La sesión expiró. Iniciá sesión nuevamente.", "session_expired")
        activity = reported_activity_at(request, now=now)
        if activity is not None and activity.timestamp() > last:
            session[SESSION_ACTIVITY_KEY] = activity.timestamp()
        return result
