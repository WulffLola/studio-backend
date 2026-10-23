import pytest
from django.urls import reverse
from .models import Teacher

@pytest.mark.django_db
class TestTeacherSoftDelete:

    def test_delete_sets_deleted(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        teacher.refresh_from_db()
        assert teacher.deleted is not None

    def test_objects_hides_deleted(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        assert not Teacher.objects.filter(pk=teacher.pk).exists()

    def test_all_objects_includes_deleted(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        assert Teacher.all_objects.filter(pk=teacher.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        assert Teacher.all_objects.dead().filter(pk=teacher.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        assert not Teacher.all_objects.alive().filter(pk=teacher.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        qs = Teacher.all_objects.for_user(admin_user)
        assert qs.filter(pk=teacher.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        qs = Teacher.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=teacher.pk).exists()

    def test_restore(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        teacher.restore()
        teacher.refresh_from_db()
        assert teacher.deleted is None

    def test_hard_delete_removes_from_db(self):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        pk = teacher.pk
        teacher.hard_delete()
        assert not Teacher.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestTeachersViewForUser:
    URL = 'teachers-list'

    def test_admin_list_includes_deleted(self, admin_client):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert teacher.id in ids

    def test_consultor_list_excludes_deleted(self, consultor_client):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        teacher.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert teacher.id not in ids

    def test_delete_endpoint_is_soft_delete(self, admin_client):
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        url = reverse('teachers-detail', args=[teacher.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Teacher.all_objects.filter(pk=teacher.pk).exists()
        teacher.refresh_from_db()
        assert teacher.deleted is not None

    def test_create_teacher_duplicate_dni(self, admin_client):
        Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        url = reverse(self.URL)
        data = {
            'name': 'Test',
            'last_name': 'Teacher',
            'dni': '11111111'
        }
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert "Ya existe un profesor con ese DNI" in response.data['error']

    def test_destroy_cascading_soft_delete(self, admin_client, slot):
        from apps.teachers_turn.models import TeachersTurn
        teacher = Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')
        turn = TeachersTurn.objects.create(teacher=teacher, slot=slot)
        
        url = reverse('teachers-detail', args=[teacher.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        
        turn.refresh_from_db()
        assert turn.deleted is not None
