import pytest
from .models import Status


@pytest.mark.django_db
class TestStatusSoftDelete:

    def test_delete_sets_deleted(self):
        s = Status.objects.create(status='Disponible')
        s.delete()
        s.refresh_from_db()
        assert s.deleted is not None

    def test_objects_hides_deleted(self):
        s = Status.objects.create(status='Disponible')
        s.delete()
        assert not Status.objects.filter(pk=s.pk).exists()

    def test_all_objects_includes_deleted(self):
        s = Status.objects.create(status='Disponible')
        s.delete()
        assert Status.all_objects.filter(pk=s.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        s = Status.objects.create(status='Disponible')
        s.delete()
        assert Status.all_objects.dead().filter(pk=s.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        s = Status.objects.create(status='Disponible')
        s.delete()
        assert not Status.all_objects.alive().filter(pk=s.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        s = Status.objects.create(status='Disponible')
        s.delete()
        qs = Status.all_objects.for_user(admin_user)
        assert qs.filter(pk=s.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        s = Status.objects.create(status='Disponible')
        s.delete()
        qs = Status.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=s.pk).exists()

    def test_restore(self):
        s = Status.objects.create(status='Disponible')
        s.delete()
        s.restore()
        s.refresh_from_db()
        assert s.deleted is None

    def test_hard_delete_removes_from_db(self):
        s = Status.objects.create(status='Disponible')
        pk = s.pk
        s.hard_delete()
        assert not Status.all_objects.filter(pk=pk).exists()
