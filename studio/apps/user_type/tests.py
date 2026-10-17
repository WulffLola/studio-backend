import pytest
from rest_framework import viewsets
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from apps.user_type.permisos import (
    StudentReadMixin, IsStudent, IsAdministrador, IsConsultor, IsSuper,
)


class _DummyViewSet(StudentReadMixin, viewsets.ModelViewSet):
    write_permission = IsAdministrador | IsConsultor | IsSuper


def _check(action, user):
    """Construye el/los permiso(s) que el mixin devolvería para `action` y
    evalúa has_permission con un request autenticado como `user`."""
    vs = _DummyViewSet()
    vs.action = action
    req = APIRequestFactory().get('/') if action in ('list', 'retrieve') else APIRequestFactory().post('/')
    drf_req = APIView().initialize_request(req)
    drf_req.user = user
    perms = vs.get_permissions()
    return all(p.has_permission(drf_req, vs) for p in perms)


@pytest.mark.django_db
@pytest.mark.parametrize('action', ['list', 'retrieve'])
def test_student_allowed_on_read(action, student_user):
    assert _check(action, student_user) is True


@pytest.mark.django_db
@pytest.mark.parametrize('action', ['create', 'update', 'partial_update', 'destroy'])
def test_student_denied_on_write(action, student_user):
    assert _check(action, student_user) is False


@pytest.mark.django_db
@pytest.mark.parametrize('action', ['list', 'create'])
def test_admin_allowed_on_both(action, admin_user):
    assert _check(action, admin_user) is True


@pytest.mark.django_db
class TestMergeDuplicateStudentType:
    """merge_duplicate_student_type: unifica el tipo duplicado 'Student' en el
    canónico 'Estudiante', reasignando usuarios y borrando la fila."""

    def _merge(self):
        from django.apps import apps as global_apps
        from apps.user_type.dedupe import merge_duplicate_student_type
        return merge_duplicate_student_type(global_apps)

    def test_reasigna_usuarios_y_borra_duplicado(self):
        from apps.user_type.models import UserType
        from apps.users.models import CustomUser
        student = UserType.objects.create(user_type_name='Student')
        estudiante = UserType.objects.create(user_type_name='Estudiante')
        u = CustomUser.objects.create_user(
            email='dup@test.com', password='x', name='D', last_name='U',
            dni='55667788', tipo_usuario=student,
        )
        reassigned = self._merge()
        assert reassigned == 1
        assert not UserType.objects.filter(user_type_name='Student').exists()
        u.refresh_from_db()
        assert u.tipo_usuario_id == estudiante.id
        assert u.is_student_user

    def test_noop_si_no_hay_student(self):
        from apps.user_type.models import UserType
        UserType.objects.create(user_type_name='Estudiante')
        reassigned = self._merge()
        assert reassigned == 0
        assert UserType.objects.filter(user_type_name='Estudiante').count() == 1
        assert not UserType.objects.filter(user_type_name='Student').exists()

    def test_reasigna_usuarios_soft_deleted_sin_hard_delete(self):
        """Un usuario soft-deleted que apunta a 'Student' debe reasignarse a
        'Estudiante' y NO ser hard-borrado por el cascade al eliminar la fila."""
        from apps.user_type.models import UserType
        from apps.users.models import CustomUser
        student = UserType.objects.create(user_type_name='Student')
        estudiante = UserType.objects.create(user_type_name='Estudiante')
        u = CustomUser.objects.create_user(
            email='softdup@test.com', password='x', name='S', last_name='D',
            dni='77889900', tipo_usuario=student,
        )
        u.delete()  # soft-delete
        self._merge()
        assert not UserType.objects.filter(user_type_name='Student').exists()
        # el usuario sigue existiendo (no hard-borrado) y quedó reasignado
        u_db = CustomUser.all_objects.get(pk=u.pk)
        assert u_db.tipo_usuario_id == estudiante.id

    def test_crea_estudiante_si_falta_y_reasigna(self):
        from apps.user_type.models import UserType
        from apps.users.models import CustomUser
        student = UserType.objects.create(user_type_name='Student')
        u = CustomUser.objects.create_user(
            email='dup2@test.com', password='x', name='D', last_name='U',
            dni='66778899', tipo_usuario=student,
        )
        reassigned = self._merge()
        assert reassigned == 1
        estudiante = UserType.objects.get(user_type_name='Estudiante')
        assert not UserType.objects.filter(user_type_name='Student').exists()
        u.refresh_from_db()
        assert u.tipo_usuario_id == estudiante.id


# None == None no debe otorgar permisos de rol

def _req(user):
    req = APIRequestFactory().get('/')
    req.user = user
    return req


@pytest.mark.django_db
@pytest.mark.parametrize('perm', [IsAdministrador, IsConsultor, IsSuper])
def test_role_perm_denies_null_tipo_usuario_without_usertype_rows(perm):
    from apps.user_type.models import UserType
    from apps.users.models import CustomUser
    UserType.objects.all().delete()
    user = CustomUser.objects.create_user(
        email='sintipo@test.com', password='test123',
        name='Sin', last_name='Tipo', dni='11111111',
    )
    assert user.tipo_usuario_id is None
    assert perm().has_permission(_req(user), None) is False


@pytest.mark.django_db
def test_admin_perm_allows_administrador_and_denies_other_roles():
    from apps.user_type.models import UserType
    from apps.users.models import CustomUser
    admin_type, _ = UserType.objects.get_or_create(user_type_name='Administrador')
    UserType.objects.get_or_create(user_type_name='Consultor')
    UserType.objects.get_or_create(user_type_name='Super')
    user = CustomUser.objects.create_user(
        email='admin288@test.com', password='test123',
        name='Admin', last_name='Uno', dni='22222222',
        tipo_usuario=admin_type,
    )
    req = _req(user)
    assert IsAdministrador().has_permission(req, None) is True
    assert IsConsultor().has_permission(req, None) is False
    assert IsSuper().has_permission(req, None) is False


@pytest.mark.django_db
@pytest.mark.parametrize('role_name,granted_cls,denied', [
    ('Administrador', IsAdministrador, (IsConsultor, IsSuper)),
    ('Consultor', IsConsultor, (IsAdministrador, IsSuper)),
    ('Super', IsSuper, (IsAdministrador, IsConsultor)),
])
def test_role_perm_positive_per_role(role_name, granted_cls, denied):
    from apps.user_type.models import UserType
    from apps.users.models import CustomUser
    for n in ('Administrador', 'Consultor', 'Super'):
        UserType.objects.get_or_create(user_type_name=n)
    user = CustomUser.objects.create_user(
        email='rol288@test.com', password='test123',
        name='Rol', last_name='Test', dni='33333333',
        tipo_usuario=UserType.objects.get(user_type_name=role_name),
    )
    req = _req(user)
    assert granted_cls().has_permission(req, None) is True
    for cls in denied:
        assert cls().has_permission(req, None) is False
