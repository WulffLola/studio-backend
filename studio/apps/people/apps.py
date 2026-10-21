from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.people'

    def ready(self):
        import apps.people.signals  # noqa: F401
