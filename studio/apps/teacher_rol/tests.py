import pytest
from .models import Rol


@pytest.mark.django_db
class TestRolSoftDelete:

    def test_delete_sets_deleted(self):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        rol.refresh_from_db()
        assert rol.deleted is not None

    def test_objects_hides_deleted(self):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        assert not Rol.objects.filter(pk=rol.pk).exists()

    def test_all_objects_includes_deleted(self):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        assert Rol.all_objects.filter(pk=rol.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        assert Rol.all_objects.dead().filter(pk=rol.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        assert not Rol.all_objects.alive().filter(pk=rol.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        qs = Rol.all_objects.for_user(admin_user)
        assert qs.filter(pk=rol.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        qs = Rol.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=rol.pk).exists()

    def test_restore(self):
        rol = Rol.objects.create(rol='Instructor')
        rol.delete()
        rol.restore()
        rol.refresh_from_db()
        assert rol.deleted is None

    def test_hard_delete_removes_from_db(self):
        rol = Rol.objects.create(rol='Instructor')
        pk = rol.pk
        rol.hard_delete()
        assert not Rol.all_objects.filter(pk=pk).exists()
