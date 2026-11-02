import pytest
from django.urls import reverse
from apps.posts.models import Post


LIST_URL = 'posts-list'
DETAIL_URL = 'posts-detail'


def make_post(**kwargs):
    defaults = {'title': 'Test Post', 'caption': 'Some caption', 'status': Post.STATUS_ACTIVE}
    defaults.update(kwargs)
    return Post.objects.create(**defaults)


# Soft-delete

@pytest.mark.django_db
class TestPostSoftDelete:

    def test_delete_sets_deleted_at(self):
        post = make_post()
        post.delete()
        post.refresh_from_db()
        assert post.deleted_at is not None

    def test_delete_sets_status_deleted(self):
        post = make_post()
        post.delete()
        post.refresh_from_db()
        assert post.status == Post.STATUS_DELETED

    def test_objects_hides_deleted(self):
        post = make_post()
        post.delete()
        assert not Post.objects.filter(pk=post.pk).exists()

    def test_all_objects_includes_deleted(self):
        post = make_post()
        post.delete()
        assert Post.all_objects.filter(pk=post.pk).exists()

    def test_all_objects_dead_returns_deleted(self):
        post = make_post()
        post.delete()
        assert Post.all_objects.dead().filter(pk=post.pk).exists()

    def test_all_objects_alive_excludes_deleted(self):
        post = make_post()
        post.delete()
        assert not Post.all_objects.alive().filter(pk=post.pk).exists()

    def test_restore_clears_deleted_at(self):
        post = make_post()
        post.delete()
        post.restore()
        post.refresh_from_db()
        assert post.deleted_at is None

    def test_restore_sets_status_draft(self):
        post = make_post()
        post.delete()
        post.restore()
        post.refresh_from_db()
        assert post.status == Post.STATUS_DRAFT

    def test_hard_delete_removes_from_db(self):
        post = make_post()
        pk = post.pk
        post.hard_delete()
        assert not Post.all_objects.filter(pk=pk).exists()


# for_user visibility

@pytest.mark.django_db
class TestPostForUser:

    def test_admin_sees_deleted(self, admin_user):
        post = make_post()
        post.delete()
        qs = Post.all_objects.for_user(admin_user)
        assert qs.filter(pk=post.pk).exists()

    def test_consultor_excludes_deleted(self, consultor_user):
        post = make_post()
        post.delete()
        qs = Post.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=post.pk).exists()


# API: list / retrieve

@pytest.mark.django_db
class TestPostListRetrieve:

    def test_unauthenticated_cannot_list(self):
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.get(reverse(LIST_URL))
        assert response.status_code in (401, 403)

    def test_consultor_can_list(self, consultor_client):
        make_post(title='Visible Post')
        response = consultor_client.get(reverse(LIST_URL))
        assert response.status_code == 200

    def test_admin_sees_deleted_in_list(self, admin_client):
        post = make_post(title='Will be deleted')
        post.delete()
        response = admin_client.get(reverse(LIST_URL))
        ids = [item['id'] for item in response.data]
        assert post.id in ids

    def test_consultor_excludes_deleted_in_list(self, consultor_client):
        post = make_post(title='Will be deleted')
        post.delete()
        response = consultor_client.get(reverse(LIST_URL))
        ids = [item['id'] for item in response.data]
        assert post.id not in ids

    def test_filter_by_title(self, consultor_client):
        make_post(title='Dance Workshop')
        make_post(title='Pilates Class')
        response = consultor_client.get(reverse(LIST_URL), {'title': 'Dance'})
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['title'] == 'Dance Workshop'

    def test_filter_by_status(self, consultor_client):
        make_post(title='Active Post', status=Post.STATUS_ACTIVE)
        make_post(title='Draft Post', status=Post.STATUS_DRAFT)
        response = consultor_client.get(reverse(LIST_URL), {'status': Post.STATUS_DRAFT})
        assert response.status_code == 200
        assert all(item['status'] == Post.STATUS_DRAFT for item in response.data)


# API: create

@pytest.mark.django_db
class TestPostCreate:

    def test_admin_can_create(self, admin_client):
        response = admin_client.post(
            reverse(LIST_URL),
            data={'title': 'New Post', 'status': Post.STATUS_ACTIVE},
            format='json',
        )
        assert response.status_code == 201
        assert Post.objects.filter(title='New Post').exists()

    def test_consultor_cannot_create(self, consultor_client):
        response = consultor_client.post(
            reverse(LIST_URL),
            data={'title': 'New Post', 'status': Post.STATUS_ACTIVE},
            format='json',
        )
        assert response.status_code in (401, 403)

    def test_create_requires_title(self, admin_client):
        response = admin_client.post(
            reverse(LIST_URL),
            data={'status': Post.STATUS_ACTIVE},
            format='json',
        )
        assert response.status_code == 400


# API: update / partial_update

@pytest.mark.django_db
class TestPostUpdate:

    def test_admin_can_patch(self, admin_client):
        post = make_post()
        url = reverse(DETAIL_URL, args=[post.pk])
        response = admin_client.patch(url, data={'title': 'Updated'}, format='json')
        assert response.status_code == 200
        post.refresh_from_db()
        assert post.title == 'Updated'

    def test_consultor_cannot_patch(self, consultor_client):
        post = make_post()
        url = reverse(DETAIL_URL, args=[post.pk])
        response = consultor_client.patch(url, data={'title': 'Updated'}, format='json')
        assert response.status_code in (401, 403)


# API: delete

@pytest.mark.django_db
class TestPostDelete:

    def test_delete_endpoint_is_soft_delete(self, admin_client):
        post = make_post()
        url = reverse(DETAIL_URL, args=[post.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert Post.all_objects.filter(pk=post.pk).exists()
        post.refresh_from_db()
        assert post.deleted_at is not None

    def test_consultor_cannot_delete(self, consultor_client):
        post = make_post()
        url = reverse(DETAIL_URL, args=[post.pk])
        response = consultor_client.delete(url)
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestPostCaptionOptionalKAN249:
    """El campo caption de /posts/ es opcional: se puede omitir, enviar "" o null
    (null se normaliza a ""). Con caption funciona normal. title sigue requerido."""

    def _create(self, admin_client, data):
        return admin_client.post(reverse(LIST_URL), data={'title': 'P', **data}, format='json')

    def test_sin_caption(self, admin_client):
        resp = self._create(admin_client, {})
        assert resp.status_code == 201
        assert resp.data['caption'] == ''

    def test_caption_vacio(self, admin_client):
        resp = self._create(admin_client, {'caption': ''})
        assert resp.status_code == 201
        assert resp.data['caption'] == ''

    def test_caption_null_se_normaliza(self, admin_client):
        resp = self._create(admin_client, {'caption': None})
        assert resp.status_code == 201
        assert resp.data['caption'] == ''

    def test_caption_con_texto(self, admin_client):
        resp = self._create(admin_client, {'caption': 'Hola mundo'})
        assert resp.status_code == 201
        assert resp.data['caption'] == 'Hola mundo'

    def test_title_sigue_requerido(self, admin_client):
        resp = admin_client.post(reverse(LIST_URL), data={'caption': 'x'}, format='json')
        assert resp.status_code == 400

    def test_patch_caption_null(self, admin_client):
        post = make_post(caption='algo')
        resp = admin_client.patch(reverse(DETAIL_URL, args=[post.pk]), data={'caption': None}, format='json')
        assert resp.status_code == 200
        assert resp.data['caption'] == ''
