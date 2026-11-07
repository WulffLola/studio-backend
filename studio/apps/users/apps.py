from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        import apps.users.signals  # noqa: F401
        from django.contrib.auth.signals import user_logged_in
        from .authentication import stamp_cookie_session
        user_logged_in.connect(stamp_cookie_session, dispatch_uid="users.stamp_cookie_session")
