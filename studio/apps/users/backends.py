from django.contrib.auth.backends import ModelBackend

from . import lockout


class LockoutModelBackend(ModelBackend):
    """ModelBackend con el mismo bloqueo que la API: cubre los logins que usan
    django.contrib.auth.authenticate() (p. ej. /api-auth/login/)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        ident = username or kwargs.get(self._username_field())
        key = lockout.account_key(ident)
        try:
            lockout.check(request, key)
        except lockout.AuthLocked:
            return None
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is None:
            lockout.register_failure(request, key)
        else:
            lockout.register_success(key)
        return user

    @staticmethod
    def _username_field():
        from django.contrib.auth import get_user_model
        return get_user_model().USERNAME_FIELD
