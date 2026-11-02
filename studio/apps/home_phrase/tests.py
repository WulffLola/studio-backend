import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from .models import HomePhrase


@pytest.mark.django_db
class TestHomePhraseView:
    LIST_URL = 'home-phrase-list'
    DETAIL_URL = 'home-phrase-detail'

    def test_anonymous_can_read(self, db):
        client = APIClient()
        response = client.get(reverse(self.LIST_URL))
        assert response.status_code == 200

    def test_admin_can_create(self, admin_client, db):
        response = admin_client.post(
            reverse(self.LIST_URL),
            data={'title': 'Bienvenida', 'phrase': 'Hola a todos'},
            format='json',
        )
        assert response.status_code == 201
        assert HomePhrase.objects.count() == 1

    def test_admin_can_update_phrase(self, admin_client, db):
        hp = HomePhrase.objects.create(title='Viejo', phrase='frase vieja')
        response = admin_client.patch(
            reverse(self.DETAIL_URL, args=[hp.pk]),
            data={'phrase': 'frase nueva'},
            format='json',
        )
        assert response.status_code == 200
        hp.refresh_from_db()
        assert hp.phrase == 'frase nueva'

    def test_admin_can_update_title(self, admin_client, db):
        hp = HomePhrase.objects.create(title='Viejo', phrase='frase')
        response = admin_client.patch(
            reverse(self.DETAIL_URL, args=[hp.pk]),
            data={'title': 'Nuevo título'},
            format='json',
        )
        assert response.status_code == 200
        hp.refresh_from_db()
        assert hp.title == 'Nuevo título'

    def test_admin_can_toggle_is_active(self, admin_client, db):
        hp = HomePhrase.objects.create(phrase='frase', is_active=True)
        response = admin_client.patch(
            reverse(self.DETAIL_URL, args=[hp.pk]),
            data={'is_active': False},
            format='json',
        )
        assert response.status_code == 200
        hp.refresh_from_db()
        assert hp.is_active is False

    def test_response_includes_title_and_is_active(self, admin_client, db):
        HomePhrase.objects.create(title='Bienvenida', phrase='Hola', is_active=True)
        response = admin_client.get(reverse(self.LIST_URL))
        item = response.data[0]
        assert 'title' in item
        assert 'is_active' in item

    def test_is_active_defaults_to_true(self, db):
        hp = HomePhrase.objects.create(phrase='sin is_active explícito')
        assert hp.is_active is True

    def test_title_defaults_to_empty(self, db):
        hp = HomePhrase.objects.create(phrase='sin título')
        assert hp.title == ''

    def test_anonymous_cannot_update(self, db):
        hp = HomePhrase.objects.create(phrase='original')
        response = APIClient().patch(
            reverse(self.DETAIL_URL, args=[hp.pk]),
            data={'phrase': 'hack'},
            format='json',
        )
        assert response.status_code in (401, 403)
