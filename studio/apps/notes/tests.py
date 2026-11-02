import pytest
from django.urls import reverse
from .models import Note


# Modelo
# Por qué: se eliminó el soft delete (deleted_at, estado 'eliminado').
# Ahora Note usa borrado físico estándar de Django.

@pytest.mark.django_db
class TestNoteModel:

    def test_default_estado_is_borrador(self):
        note = Note.objects.create(titulo='Test', descripcion='Desc')
        assert note.estado == 'borrador'

    def test_estado_choices_no_include_eliminado(self):
        choices = dict(Note.ESTADO_CHOICES)
        assert 'eliminado' not in choices

    def test_valid_estado_choices(self):
        choices = dict(Note.ESTADO_CHOICES)
        assert 'borrador' in choices
        assert 'en_pausa' in choices
        assert 'activo' in choices

    def test_delete_removes_from_db(self):
        note = Note.objects.create(titulo='Test', descripcion='Desc')
        pk = note.pk
        note.delete()
        assert not Note.objects.filter(pk=pk).exists()

    def test_no_deleted_at_field(self):
        note = Note.objects.create(titulo='Test', descripcion='Desc')
        assert not hasattr(note, 'deleted_at')

    def test_str_returns_titulo(self):
        note = Note.objects.create(titulo='Mi Nota', descripcion='Desc')
        assert str(note) == 'Mi Nota'


# Vista

@pytest.mark.django_db
class TestNoteView:
    URL = 'notes-list'

    def test_list_returns_200(self, admin_client):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200

    def test_create_note(self, admin_client):
        data = {'titulo': 'Nueva nota', 'descripcion': 'Contenido', 'estado': 'activo'}
        response = admin_client.post(reverse(self.URL), data=data, format='json')
        assert response.status_code == 201
        assert Note.objects.filter(titulo='Nueva nota').exists()

    def test_delete_endpoint_removes_from_db(self, admin_client):
        note = Note.objects.create(titulo='Para borrar', descripcion='Desc')
        url = reverse('notes-detail', args=[note.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert not Note.objects.filter(pk=note.pk).exists()

    def test_unauthenticated_returns_403(self):
        from rest_framework.test import APIClient
        response = APIClient().get(reverse(self.URL))
        assert response.status_code in (401, 403)

    def test_update_estado(self, admin_client):
        note = Note.objects.create(titulo='Test', descripcion='Desc', estado='borrador')
        url = reverse('notes-detail', args=[note.pk])
        response = admin_client.patch(url, data={'estado': 'activo'}, format='json')
        assert response.status_code == 200
        note.refresh_from_db()
        assert note.estado == 'activo'
