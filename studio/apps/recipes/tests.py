import pytest
from django.urls import reverse
from .models import Recipe


# Modelo
# Por qué: se eliminó el soft delete (deleted_at, estado 'eliminado').
# Ahora Recipe usa borrado físico estándar de Django.

@pytest.mark.django_db
class TestRecipeModel:

    def test_default_estado_is_borrador(self):
        recipe = Recipe.objects.create(titulo='Test', descripcion='Desc', ingredientes='I', pasos='P')
        assert recipe.estado == 'borrador'

    def test_estado_choices_no_include_eliminado(self):
        choices = dict(Recipe.ESTADO_CHOICES)
        assert 'eliminado' not in choices

    def test_valid_estado_choices(self):
        choices = dict(Recipe.ESTADO_CHOICES)
        assert 'borrador' in choices
        assert 'en_pausa' in choices
        assert 'activo' in choices

    def test_delete_removes_from_db(self):
        recipe = Recipe.objects.create(titulo='Test', descripcion='Desc', ingredientes='I', pasos='P')
        pk = recipe.pk
        recipe.delete()
        assert not Recipe.objects.filter(pk=pk).exists()

    def test_no_deleted_at_field(self):
        recipe = Recipe.objects.create(titulo='Test', descripcion='Desc', ingredientes='I', pasos='P')
        assert not hasattr(recipe, 'deleted_at')

    def test_str_returns_titulo(self):
        recipe = Recipe.objects.create(titulo='Mi Receta', descripcion='Desc', ingredientes='I', pasos='P')
        assert str(recipe) == 'Mi Receta'


# Vista

@pytest.mark.django_db
class TestRecipeView:
    URL = 'recipes-list'

    def test_list_returns_200(self, admin_client):
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200

    def test_create_recipe(self, admin_client):
        data = {
            'titulo': 'Nueva receta',
            'descripcion': 'Desc',
            'ingredientes': 'Agua, sal',
            'pasos': '1. Mezclar',
            'estado': 'activo',
        }
        response = admin_client.post(reverse(self.URL), data=data, format='json')
        assert response.status_code == 201
        assert Recipe.objects.filter(titulo='Nueva receta').exists()

    def test_delete_endpoint_removes_from_db(self, admin_client):
        recipe = Recipe.objects.create(titulo='Para borrar', descripcion='Desc', ingredientes='I', pasos='P')
        url = reverse('recipes-detail', args=[recipe.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert not Recipe.objects.filter(pk=recipe.pk).exists()

    def test_unauthenticated_returns_403(self):
        from rest_framework.test import APIClient
        response = APIClient().get(reverse(self.URL))
        assert response.status_code in (401, 403)

    def test_update_estado(self, admin_client):
        recipe = Recipe.objects.create(titulo='Test', descripcion='Desc', ingredientes='I', pasos='P', estado='borrador')
        url = reverse('recipes-detail', args=[recipe.pk])
        response = admin_client.patch(url, data={'estado': 'activo'}, format='json')
        assert response.status_code == 200
        recipe.refresh_from_db()
        assert recipe.estado == 'activo'
