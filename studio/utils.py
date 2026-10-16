from django.db import models
from django.utils import timezone


ADMIN_USER_TYPES = [1, 2]  # Super, Administrador


# Mixin de borrado lógico

class SoftDeleteMixin(models.Model):
    """
    Centraliza el borrado lógico (delete / hard_delete / restore) para evitar
    repetir el mismo bloque en cada modelo.

    Cada modelo concreto declara su propio campo de borrado; por defecto se
    asume `deleted`. Si usa otro nombre, sobreescribe ``SOFT_DELETE_FIELD``.

    El valor escrito respeta el tipo del campo: ``date`` para ``DateField`` y
    ``datetime`` para ``DateTimeField`` (evita la coerción implícita anterior).

    Es abstracto y no declara campos, por lo que no genera migraciones.
    """
    SOFT_DELETE_FIELD = 'deleted'

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        field = self._meta.get_field(self.SOFT_DELETE_FIELD)
        value = timezone.now()
        # DateTimeField hereda de DateField -> aislar el DateField "puro".
        if isinstance(field, models.DateField) and not isinstance(field, models.DateTimeField):
            value = value.date()
        setattr(self, self.SOFT_DELETE_FIELD, value)
        self.save(update_fields=[self.SOFT_DELETE_FIELD])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        setattr(self, self.SOFT_DELETE_FIELD, None)
        self.save(update_fields=[self.SOFT_DELETE_FIELD])


# Para modelos con campo `deleted_at` (notes, recipes)

class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def for_user(self, user):
        if user.tipo_usuario_id in ADMIN_USER_TYPES:
            return self.all()
        return self.alive()


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


# Para modelos con campo `deleted` (resto de las apps)

class DeletedQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted__isnull=True)

    def dead(self):
        return self.filter(deleted__isnull=False)

    def for_user(self, user):
        if user.tipo_usuario_id in ADMIN_USER_TYPES:
            return self.all()
        return self.alive()


class DeletedManager(models.Manager):
    def get_queryset(self):
        return DeletedQuerySet(self.model, using=self._db).alive()
