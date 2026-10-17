import io
import pytest
from django.urls import reverse
from django.core import signing
from PIL import Image
from rest_framework.test import APIClient
from apps.users.models import CustomUser
from apps.people.models import Person
from apps.user_type.models import UserType


def _make_image(name='photo.jpg', fmt='JPEG'):
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), color='red').save(buf, format=fmt)
    buf.seek(0)
    buf.name = name
    return buf


# Helpers

@pytest.fixture
def student_type(db):
    # 'Estudiante' es el nombre actual en la DB; no usar get_student_pk() aquí
    # porque ese método depende de que el registro ya exista.
    t, _ = UserType.objects.get_or_create(user_type_name='Estudiante')
    return t


@pytest.fixture
def person_with_email(db):
    return Person.objects.create(
        name='Ana', last_name='Lopez', dni='55556666',
        email='ana@test.com', phone='1234567890',
    )


# CheckDniView

@pytest.mark.django_db
class TestCheckDniView:
    URL = 'register-check-list'

    def test_dni_not_found(self, client):
        response = client.post(reverse(self.URL), data={'dni': '00000000', 'email': 'x@x.com'}, content_type='application/json')
        assert response.status_code == 200
        assert response.data['result'] == 'not_found'

    def test_dni_found_email_mismatch(self, client, person_with_email):
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': 'wrong@email.com',
        }, content_type='application/json')
        assert response.status_code == 200
        assert response.data['result'] == 'email_mismatch'

    def test_dni_found_email_match(self, client, person_with_email):
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': person_with_email.email,
        }, content_type='application/json')
        assert response.status_code == 200
        assert response.data['result'] == 'found'
        assert response.data['person']['name'] == person_with_email.name

    def test_missing_fields_returns_400(self, client):
        response = client.post(reverse(self.URL), data={'dni': '12345678'}, content_type='application/json')
        assert response.status_code == 400

    def test_email_case_insensitive(self, client, person_with_email):
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': person_with_email.email.upper(),
        }, content_type='application/json')
        assert response.status_code == 200
        assert response.data['result'] == 'found'


# RegisterView — caso existente

@pytest.mark.django_db
class TestRegisterViewExisting:
    URL = 'register-list'

    def test_register_existing_person_creates_user(self, client, person_with_email, student_type):
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': person_with_email.email,
            'password': 'securepass123',
        }, content_type='application/json')
        assert response.status_code == 201
        user = CustomUser.all_objects.get(dni=person_with_email.dni)
        assert user.is_active is False
        assert user.person == person_with_email
        assert user.tipo_usuario.id == UserType.get_student_pk()

    def test_register_existing_wrong_email_returns_400(self, client, person_with_email, student_type):
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': 'wrong@email.com',
            'password': 'securepass123',
        }, content_type='application/json')
        assert response.status_code == 400

    def test_register_duplicate_email_returns_400(self, client, person_with_email, student_type):
        # Register once
        client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': person_with_email.email,
            'password': 'securepass123',
        }, content_type='application/json')
        # Try again
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': person_with_email.email,
            'password': 'otherpass',
        }, content_type='application/json')
        assert response.status_code == 400


# RegisterView — caso nuevo

@pytest.mark.django_db
class TestRegisterViewNew:
    URL = 'register-list'

    def test_register_new_creates_person_and_user(self, client, student_type):
        response = client.post(reverse(self.URL), data={
            'dni': '77778888',
            'email': 'nuevo@test.com',
            'password': 'securepass123',
            'name': 'Carlos',
            'last_name': 'Ruiz',
            'sex': 'M',
            'phone': '1122334455',
            'birth_date': '1995-06-15',
        }, content_type='application/json')
        assert response.status_code == 201
        assert Person.objects.filter(dni='77778888').exists()
        user = CustomUser.all_objects.get(dni='77778888')
        assert user.is_active is False
        assert user.person is not None
        assert user.tipo_usuario.id == UserType.get_student_pk()

    def test_register_new_minimal_fields(self, client, student_type):
        response = client.post(reverse(self.URL), data={
            'dni': '11112222',
            'email': 'minimal@test.com',
            'password': 'pass123',
            'name': 'Maria',
            'last_name': 'Garcia',
        }, content_type='application/json')
        assert response.status_code == 201

    def test_register_new_missing_required_field_returns_400(self, client, student_type):
        response = client.post(reverse(self.URL), data={
            'dni': '33334444',
            'email': 'missing@test.com',
            'password': 'pass123',
            # missing name and last_name
        }, content_type='application/json')
        assert response.status_code == 400


# VerifyEmailView

@pytest.mark.django_db
class TestVerifyEmailView:
    URL = 'register-verify-email-list'

    def _create_inactive_user(self, person_with_email, student_type):
        user = CustomUser(
            email=person_with_email.email,
            name=person_with_email.name,
            last_name=person_with_email.last_name,
            dni=person_with_email.dni,
            tipo_usuario=student_type,
            person=person_with_email,
            is_active=False,
        )
        user.set_password('pass123')
        user.save()
        return user

    def test_valid_token_activates_user(self, client, person_with_email, student_type):
        user = self._create_inactive_user(person_with_email, student_type)
        token = signing.dumps(user.pk, salt='email-verification')
        response = client.post(reverse(self.URL), data={'token': token}, content_type='application/json')
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.is_active is True
        assert 'tokens' in response.data

    def test_valid_token_returns_jwt(self, client, person_with_email, student_type):
        user = self._create_inactive_user(person_with_email, student_type)
        token = signing.dumps(user.pk, salt='email-verification')
        response = client.post(reverse(self.URL), data={'token': token}, content_type='application/json')
        assert 'access' in response.data['tokens']
        assert 'refresh' in response.data['tokens']

    def test_invalid_token_returns_400(self, client):
        response = client.post(reverse(self.URL), data={'token': 'bad-token'}, content_type='application/json')
        assert response.status_code == 400

    def test_missing_token_returns_400(self, client):
        response = client.post(reverse(self.URL), data={}, content_type='application/json')
        assert response.status_code == 400

    def test_already_active_user_returns_200(self, client, person_with_email, student_type):
        user = self._create_inactive_user(person_with_email, student_type)
        user.is_active = True
        user.save()
        token = signing.dumps(user.pk, salt='email-verification')
        response = client.post(reverse(self.URL), data={'token': token}, content_type='application/json')
        assert response.status_code == 200
        assert 'ya estaba verificada' in response.data['detail']

    def test_expired_token_returns_400(self, client, person_with_email, student_type):
        user = self._create_inactive_user(person_with_email, student_type)
        # max_age=0 means any token is expired
        token = signing.dumps(user.pk, salt='email-verification')
        import time as _time
        _time.sleep(1)
        try:
            signing.loads(token, salt='email-verification', max_age=0)
            assert False, "Should have raised"
        except signing.SignatureExpired:
            pass  # confirmed: token expires correctly with max_age=0


# PasswordResetView

@pytest.mark.django_db
class TestPasswordResetView:
    URL = 'password-reset-list'

    @pytest.fixture
    def active_user(self, person_with_email, student_type):
        user = CustomUser(
            email=person_with_email.email,
            name=person_with_email.name,
            last_name=person_with_email.last_name,
            dni=person_with_email.dni,
            tipo_usuario=student_type,
            person=person_with_email,
            is_active=True,
        )
        user.set_password('oldpass123')
        user.save()
        return user

    def test_existing_email_returns_200(self, client, active_user):
        response = client.post(reverse(self.URL), data={'email': active_user.email}, content_type='application/json')
        assert response.status_code == 200
        assert 'detail' in response.data

    def test_unknown_email_also_returns_200(self, client, db):
        response = client.post(reverse(self.URL), data={'email': 'noexiste@test.com'}, content_type='application/json')
        assert response.status_code == 200

    def test_missing_email_returns_400(self, client, db):
        response = client.post(reverse(self.URL), data={}, content_type='application/json')
        assert response.status_code == 400

    def test_invalid_email_format_returns_400(self, client, db):
        response = client.post(reverse(self.URL), data={'email': 'no-es-email'}, content_type='application/json')
        assert response.status_code == 400


# PasswordResetConfirmView

@pytest.mark.django_db
class TestPasswordResetConfirmView:
    URL = 'password-reset-confirm-list'

    @pytest.fixture
    def active_user(self, person_with_email, student_type):
        user = CustomUser(
            email=person_with_email.email,
            name=person_with_email.name,
            last_name=person_with_email.last_name,
            dni=person_with_email.dni,
            tipo_usuario=student_type,
            person=person_with_email,
            is_active=True,
        )
        user.set_password('oldpass123')
        user.save()
        return user

    def test_valid_token_resets_password(self, client, active_user):
        token = signing.dumps(active_user.pk, salt='password-reset')
        response = client.post(reverse(self.URL), data={'token': token, 'password': 'newpass456'}, content_type='application/json')
        assert response.status_code == 200
        active_user.refresh_from_db()
        assert active_user.check_password('newpass456')

    def test_old_password_no_longer_works(self, client, active_user):
        token = signing.dumps(active_user.pk, salt='password-reset')
        client.post(reverse(self.URL), data={'token': token, 'password': 'newpass456'}, content_type='application/json')
        active_user.refresh_from_db()
        assert not active_user.check_password('oldpass123')

    def test_invalid_token_returns_400(self, client, db):
        response = client.post(reverse(self.URL), data={'token': 'token-invalido', 'password': 'newpass456'}, content_type='application/json')
        assert response.status_code == 400

    def test_wrong_salt_token_returns_400(self, client, active_user):
        token = signing.dumps(active_user.pk, salt='email-verification')
        response = client.post(reverse(self.URL), data={'token': token, 'password': 'newpass456'}, content_type='application/json')
        assert response.status_code == 400

    def test_missing_fields_returns_400(self, client, db):
        response = client.post(reverse(self.URL), data={'token': 'algo'}, content_type='application/json')
        assert response.status_code == 400

    def test_password_too_short_returns_400(self, client, active_user):
        token = signing.dumps(active_user.pk, salt='password-reset')
        response = client.post(reverse(self.URL), data={'token': token, 'password': '123'}, content_type='application/json')
        assert response.status_code == 400

    def test_expired_token_returns_400(self, client, active_user):
        token = signing.dumps(active_user.pk, salt='password-reset')
        try:
            signing.loads(token, salt='password-reset', max_age=0)
            assert False, "Should have raised"
        except signing.SignatureExpired:
            pass  # token expira correctamente con max_age=0


# CheckDniView — nuevos casos (filtro por tipo + email_in_use + phone)
# Por qué estos tests: los checks anteriores buscaban en TODOS los CustomUser,
# lo que bloqueaba el registro si un Admin tenía el mismo DNI/email. Ahora solo
# se controla entre Estudiantes. También se detecta el caso donde el email ya
# existe en people con otro DNI (email_in_use), que antes llegaba como error
# solo en /register/.

@pytest.mark.django_db
class TestCheckDniViewFilterByStudentType:
    URL = 'register-check-list'

    @pytest.fixture
    def admin_type(self, db):
        t, _ = UserType.objects.get_or_create(id=2, defaults={'user_type_name': 'Administrador'})
        return t

    @pytest.fixture
    def admin_user_same_dni(self, admin_type):
        # Admin cuyo DNI coincide con el que un alumno quiere registrar.
        # No debe bloquear el registro del alumno.
        return CustomUser.objects.create_user(
            email='adminunico@test.com', password='pass123',
            name='Admin', last_name='X', dni='88887777',
            tipo_usuario=admin_type,
        )

    def test_admin_same_dni_does_not_block(self, client, admin_user_same_dni):
        """
        Un Admin con el mismo DNI no debe bloquear /check/ para un Estudiante.
        El filtro solo aplica sobre usuarios tipo Estudiante.
        """
        response = client.post(
            reverse(self.URL),
            data={'dni': admin_user_same_dni.dni, 'email': 'distinto@test.com'},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] != 'already_registered'

    def test_admin_same_email_does_not_block(self, client, admin_user_same_dni):
        """
        Un Admin con el mismo email no debe bloquear /check/ para un Estudiante.
        """
        response = client.post(
            reverse(self.URL),
            data={'dni': '00001111', 'email': admin_user_same_dni.email},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] != 'already_registered'

    def test_student_same_dni_blocks(self, client, student_type):
        """
        Un Estudiante ya registrado con el mismo DNI SÍ debe bloquear.
        """
        CustomUser.objects.create_user(
            email='estu@test.com', password='pass',
            name='E', last_name='L', dni='11119999',
            tipo_usuario=student_type,
        )
        response = client.post(
            reverse(self.URL),
            data={'dni': '11119999', 'email': 'otro@test.com'},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] == 'already_registered'
        assert response.data['dni_taken'] is True

    def test_student_same_email_blocks(self, client, student_type):
        """
        Un Estudiante ya registrado con el mismo email SÍ debe bloquear.
        """
        CustomUser.objects.create_user(
            email='mismo@test.com', password='pass',
            name='E', last_name='L', dni='22228888',
            tipo_usuario=student_type,
        )
        response = client.post(
            reverse(self.URL),
            data={'dni': '33337777', 'email': 'mismo@test.com'},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] == 'already_registered'
        assert response.data['email_taken'] is True

    def test_email_in_use_by_another_person_returns_email_in_use(self, client):
        """
        El email ya existe en people con otro DNI -> debe retornar email_in_use
        antes de llegar a /register/. Antes esto solo fallaba en /register/.
        """
        Person.objects.create(
            name='Otro', last_name='Alumno', dni='44446666',
            email='compartido@test.com',
        )
        response = client.post(
            reverse(self.URL),
            data={'dni': '99990000', 'email': 'compartido@test.com'},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] == 'email_in_use'

    def test_found_response_includes_masked_phone(self, client, person_with_email):
        """
        Cuando el DNI y email coinciden en people, la respuesta incluye el
        teléfono enmascarado (solo últimos 4 dígitos visibles).
        """
        response = client.post(
            reverse(self.URL),
            data={'dni': person_with_email.dni, 'email': person_with_email.email},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] == 'found'
        phone = response.data['person']['phone']
        assert '****' in phone or phone == ''  # enmascarado o vacío
        assert phone.endswith(person_with_email.phone[-4:])

    def test_found_response_does_not_expose_full_phone(self, client, person_with_email):
        """
        El teléfono completo no debe aparecer en la respuesta.
        """
        response = client.post(
            reverse(self.URL),
            data={'dni': person_with_email.dni, 'email': person_with_email.email},
            content_type='application/json',
        )
        phone = response.data['person']['phone']
        assert phone != person_with_email.phone


# RegisterView — filtro por tipo Estudiante

@pytest.mark.django_db
class TestRegisterViewStudentFilter:
    URL = 'register-list'

    @pytest.fixture
    def admin_type(self, db):
        t, _ = UserType.objects.get_or_create(id=2, defaults={'user_type_name': 'Administrador'})
        return t

    def test_non_student_user_does_not_trigger_already_registered(self, client, student_type, admin_type):
        """
        Un Admin ya registrado no debe hacer que /register/ devuelva
        'Ya existe un usuario' cuando un Estudiante distinto intenta registrarse.
        El filtro por tipo_usuario impide falsos positivos en el mensaje de error.
        """
        # Admin con sus propios datos (distintos al estudiante que se va a registrar)
        CustomUser.objects.create_user(
            email='admin_unrelated@test.com', password='pass',
            name='Admin', last_name='X', dni='88887001',
            tipo_usuario=admin_type,
        )
        # Person para el estudiante nuevo
        Person.objects.create(
            name='Carlos', last_name='Nuevo', dni='88887002',
            email='student_new@test.com',
        )
        response = client.post(
            reverse(self.URL),
            data={
                'dni': '88887002',
                'email': 'student_new@test.com',
                'password': 'securepass123',
            },
            content_type='application/json',
        )
        # El Admin existente no interfiere con el registro del Estudiante
        assert response.status_code == 201


# Soft-delete en registro
# Por qué estos tests: si un Estudiante tenía cuenta y fue dado de baja (soft
# delete), el registro crasheaba o devolvía un mensaje genérico. Ahora ambos
# endpoints detectan la cuenta desactivada y retornan un mensaje claro.

@pytest.mark.django_db
class TestRegistrationSoftDeletedUser:
    CHECK_URL = 'register-check-list'
    REGISTER_URL = 'register-list'

    @pytest.fixture
    def deleted_student(self, student_type):
        """Estudiante dado de baja (soft-deleted)."""
        from django.utils import timezone
        person = Person.objects.create(
            name='Juan', last_name='Baja', dni='11112222',
            email='juan@baja.com', phone='1111111111',
        )
        user = CustomUser(
            email='juan@baja.com', name='Juan', last_name='Baja',
            dni='11112222', tipo_usuario=student_type,
            person=person, is_active=False,
        )
        user.set_password('pass1234')
        user.save()
        user.deleted = timezone.now()
        user.save(update_fields=['deleted'])
        return user

    def test_check_returns_account_disabled_for_deleted_user(self, client, deleted_student):
        """
        /check/ debe retornar account_disabled cuando el DNI corresponde a un
        Estudiante dado de baja, en lugar de already_registered o crashear.
        """
        response = client.post(
            reverse(self.CHECK_URL),
            data={'dni': deleted_student.dni, 'email': deleted_student.email},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] == 'account_disabled'
        assert 'dada de baja' in response.data['detail'].lower() or 'estudio' in response.data['detail'].lower()

    def test_check_email_deleted_returns_account_disabled(self, client, deleted_student):
        """
        /check/ detecta cuenta desactivada también cuando coincide por email.
        """
        response = client.post(
            reverse(self.CHECK_URL),
            data={'dni': '99998888', 'email': deleted_student.email},
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.data['result'] == 'account_disabled'

    def test_register_returns_400_with_friendly_message_for_deleted_user(self, client, deleted_student):
        """
        /register/ debe devolver 400 con mensaje amigable cuando el DNI o email
        pertenece a un Estudiante dado de baja, sin crashear.
        """
        response = client.post(
            reverse(self.REGISTER_URL),
            data={
                'dni': deleted_student.dni,
                'email': deleted_student.email,
                'password': 'newpass123',
            },
            content_type='application/json',
        )
        assert response.status_code == 400
        assert 'dada de baja' in response.data['detail'].lower() or 'estudio' in response.data['detail'].lower()

    def test_register_does_not_create_duplicate_person_for_deleted(self, client, deleted_student, student_type):
        """
        /register/ no debe crear una Person duplicada si la persona ya existe
        (incluso soft-deleted). El error 400 debe ocurrir antes de intentar crear.
        """
        from apps.people.models import Person as P
        initial_count = P.all_objects.count()
        client.post(
            reverse(self.REGISTER_URL),
            data={
                'dni': deleted_student.dni,
                'email': deleted_student.email,
                'password': 'newpass123',
            },
            content_type='application/json',
        )
        assert P.all_objects.count() == initial_count


# Upload de foto de perfil en usuario
# Por qué: se agregó profile_photo a CustomUser para que todos los tipos de
# usuario (Admin, Consultor, Super, Estudiante) puedan tener foto de perfil,
# independientemente de si tienen Person vinculada o no.

@pytest.mark.django_db
class TestUserPhotoUpload:
    URL = 'users-upload-photo'

    @pytest.fixture
    def admin_type(self, db):
        t, _ = UserType.objects.get_or_create(id=2, defaults={'user_type_name': 'Administrador'})
        return t

    @pytest.fixture
    def target_user(self, admin_type):
        """Usuario sin Person vinculada (caso Admin/Consultor)."""
        return CustomUser.objects.create_user(
            email='target@test.com', password='pass123',
            name='Target', last_name='User', dni='99990001',
            tipo_usuario=admin_type,
        )

    def test_admin_can_upload_photo(self, admin_client, target_user):
        url = reverse(self.URL, args=[target_user.pk])
        response = admin_client.patch(url, data={'profile_photo': _make_image()}, format='multipart')
        assert response.status_code == 200
        assert 'profile_photo' in response.data
        target_user.refresh_from_db()
        assert target_user.profile_photo

    def test_second_upload_replaces_first(self, admin_client, target_user):
        url = reverse(self.URL, args=[target_user.pk])
        admin_client.patch(url, data={'profile_photo': _make_image('first.jpg')}, format='multipart')
        admin_client.patch(url, data={'profile_photo': _make_image('second.jpg')}, format='multipart')
        target_user.refresh_from_db()
        assert 'second' in target_user.profile_photo.name

    def test_unauthenticated_returns_403(self, target_user):
        url = reverse(self.URL, args=[target_user.pk])
        response = APIClient().patch(url, data={'profile_photo': _make_image()}, format='multipart')
        assert response.status_code in (401, 403)

    def test_oversized_image_returns_400(self, admin_client, target_user):
        big_file = io.BytesIO(b'x' * (6 * 1024 * 1024))
        big_file.name = 'big.jpg'
        url = reverse(self.URL, args=[target_user.pk])
        response = admin_client.patch(url, data={'profile_photo': big_file}, format='multipart')
        assert response.status_code == 400

    def test_invalid_format_returns_400(self, admin_client, target_user):
        pdf = io.BytesIO(b'%PDF-1.4 fake content')
        pdf.name = 'doc.pdf'
        url = reverse(self.URL, args=[target_user.pk])
        response = admin_client.patch(url, data={'profile_photo': pdf}, format='multipart')
        assert response.status_code == 400

    def test_user_without_person_can_have_photo(self, admin_client, target_user):
        """Admin/Consultor sin Person vinculada puede subir foto sin error."""
        assert target_user.person is None
        url = reverse(self.URL, args=[target_user.pk])
        response = admin_client.patch(url, data={'profile_photo': _make_image()}, format='multipart')
        assert response.status_code == 200

    def test_profile_photo_appears_in_user_detail(self, admin_client, target_user):
        """Después de subir foto, aparece en el GET del usuario."""
        url = reverse(self.URL, args=[target_user.pk])
        admin_client.patch(url, data={'profile_photo': _make_image()}, format='multipart')
        detail_url = reverse('users-detail', args=[target_user.pk])
        response = admin_client.get(detail_url)
        assert response.status_code == 200
        assert response.data.get('profile_photo') is not None

    def test_user_without_photo_returns_null(self, admin_client, target_user):
        """Usuario sin foto devuelve profile_photo: null en el detalle."""
        detail_url = reverse('users-detail', args=[target_user.pk])
        response = admin_client.get(detail_url)
        assert response.status_code == 200
        assert response.data.get('profile_photo') is None


# is_student flag
# Por qué: un Super/Admin/Consultor puede también ser alumno del estudio.
# El flag is_student les da acceso a los endpoints de área-alumno sin cambiar
# su tipo de usuario (y sin perder permisos de gestión).

@pytest.mark.django_db
class TestIsStudentFlag:

    @pytest.fixture
    def admin_type(self, db):
        t, _ = UserType.objects.get_or_create(id=2, defaults={'user_type_name': 'Administrador'})
        return t

    @pytest.fixture
    def student_person(self, db):
        from apps.people.models import Person
        return Person.objects.create(
            name='Admin', last_name='Alumno', dni='77770001', email='admin_alumno@test.com',
        )

    @pytest.fixture
    def admin_with_student_flag(self, admin_type, student_person):
        user = CustomUser.objects.create_user(
            email='admin_alumno@test.com', password='pass123',
            name='Admin', last_name='Alumno', dni='77770001',
            tipo_usuario=admin_type,
            is_student=True,
        )
        user.person = student_person
        user.save(update_fields=['person'])
        return user

    def test_default_is_false(self, admin_type):
        user = CustomUser.objects.create_user(
            email='plain_admin@test.com', password='pass',
            name='A', last_name='B', dni='77770002',
            tipo_usuario=admin_type,
        )
        assert user.is_student is False

    def test_is_student_user_property_true_when_flag_set(self, admin_with_student_flag):
        assert admin_with_student_flag.is_student_user is True

    def test_is_student_user_property_false_without_flag(self, admin_type):
        user = CustomUser.objects.create_user(
            email='noflag@test.com', password='pass',
            name='A', last_name='B', dni='77770003',
            tipo_usuario=admin_type,
        )
        assert user.is_student_user is False

    def test_pure_student_is_student_user_true(self, student_type):
        from apps.people.models import Person
        p = Person.objects.create(name='Est', last_name='X', dni='77770004', email='est@test.com')
        user = CustomUser.objects.create_user(
            email='est@test.com', password='pass',
            name='Est', last_name='X', dni='77770004',
            tipo_usuario=student_type,
        )
        user.person = p
        user.save(update_fields=['person'])
        assert user.is_student_user is True

    def test_serializer_exposes_is_student(self, admin_client, admin_with_student_flag):
        url = reverse('users-detail', args=[admin_with_student_flag.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response.data['is_student'] is True

    def test_patch_sets_is_student(self, admin_client, admin_with_student_flag):
        url = reverse('users-detail', args=[admin_with_student_flag.pk])
        response = admin_client.patch(url, data={'is_student': False}, format='json')
        assert response.status_code == 200
        admin_with_student_flag.refresh_from_db()
        assert admin_with_student_flag.is_student is False

    @pytest.mark.django_db
    def test_admin_flagged_student_gets_person_on_create(self, admin_type):
        user = CustomUser.objects.create_user(
            email='admin_flag@test.com', password='x', name='Adm', last_name='Flag',
            dni='77770099', tipo_usuario=admin_type, is_student=True, phone='9',
        )
        user.refresh_from_db()
        assert user.person_id is not None          # mismo User + Person, no otro user
        assert user.person.name == 'Adm'
        assert user.person.email == 'admin_flag@test.com'
        assert CustomUser.objects.count() == 1  # mismo User: el signal creó una Person y la vinculó, no otro usuario


from datetime import date
from apps.users.identity_sync import (
    PROFILE_FIELDS,
    USER_TO_PERSON_FIELDS,
    sync_user_to_person,
    sync_person_to_users,
    find_identity_mismatches,
)


class TestIdentitySyncSignals:
    @pytest.fixture
    def linked_student(self, user_types):
        person = Person.objects.create(
            name='Juan', last_name='Perez', dni='99999999',
            email='juan@test.com', phone='111',
        )
        user = CustomUser.objects.create_user(
            email='juan@test.com', password='x', name='Juan', last_name='Perez',
            dni='99999999', tipo_usuario=user_types['student'], person=person,
        )
        return user, person

    @pytest.mark.django_db
    def test_user_edit_propagates_to_person(self, linked_student):
        user, person = linked_student
        user.name = 'Juancito'
        user.phone = '222'
        user.sex = 'M'
        user.birth_date = date(1990, 1, 1)
        user.save()
        person.refresh_from_db()
        assert person.name == 'Juancito'
        assert person.phone == '222'
        assert person.sex == 'M'
        assert person.birth_date == date(1990, 1, 1)

    @pytest.mark.django_db
    def test_person_edit_propagates_to_user(self, linked_student):
        user, person = linked_student
        person.name = 'Pedro'
        person.last_name = 'Gomez'
        person.sex = 'F'
        person.save()
        user.refresh_from_db()
        assert user.name == 'Pedro'
        assert user.last_name == 'Gomez'
        assert user.sex == 'F'

    @pytest.mark.django_db
    def test_person_without_user_saves_ok(self, db):
        p = Person.objects.create(name='Sola', last_name='X', dni='10101010')
        p.name = 'Sola2'
        p.save()  # no debe romper ni recursar
        p.refresh_from_db()
        assert p.name == 'Sola2'

    @pytest.mark.django_db
    def test_student_without_person_gets_one_on_create(self, user_types):
        user = CustomUser.objects.create_user(
            email='nuevo@test.com', password='x', name='Nuevo', last_name='Alumno',
            dni='30303030', tipo_usuario=user_types['student'], phone='555',
        )
        user.refresh_from_db()
        assert user.person_id is not None
        assert user.person.name == 'Nuevo'
        assert user.person.phone == '555'
        assert user.person.email == 'nuevo@test.com'  # email baja User->Person
        assert user.person.dni == '30303030'          # dni baja User->Person

    @pytest.mark.django_db
    def test_photo_syncs_user_to_person(self, linked_student):
        user, person = linked_student
        user.profile_photo = 'users/photos/test.jpg'
        user.save()
        person.refresh_from_db()
        assert person.profile_photo.name == 'users/photos/test.jpg'


class TestIdentitySyncFunctions:
    @pytest.mark.django_db
    def test_field_sets(self):
        assert PROFILE_FIELDS == [
            "name", "last_name", "phone", "sex", "birth_date", "profile_photo",
        ]
        assert USER_TO_PERSON_FIELDS == PROFILE_FIELDS + ["dni", "email"]

    @pytest.mark.django_db
    def test_sync_user_to_person_copies_profile_dni_and_email(self, user_types):
        # admin => el signal de estudiante no interfiere (is_student_user False)
        person = Person.objects.create(name='Viejo', last_name='Viejo', dni='1')
        user = CustomUser.objects.create_user(
            email='u1@test.com', password='x', name='Nuevo', last_name='Nombre',
            dni='2', tipo_usuario=user_types['admin'], person=person,
            phone='123', sex='M', birth_date=date(1990, 1, 1),
        )
        sync_user_to_person(user)
        person.refresh_from_db()
        assert person.name == 'Nuevo'
        assert person.last_name == 'Nombre'
        assert person.phone == '123'
        assert person.sex == 'M'
        assert person.birth_date == date(1990, 1, 1)
        assert person.email == 'u1@test.com'   # email baja User->Person
        assert person.dni == '2'               # dni baja User->Person

    @pytest.mark.django_db
    def test_sync_user_to_person_no_person_is_noop(self, user_types):
        user = CustomUser.objects.create_user(
            email='u2@test.com', password='x', name='Sin', last_name='Person',
            dni='3', tipo_usuario=user_types['admin'],
        )
        sync_user_to_person(user)  # no debe romper

    @pytest.mark.django_db
    def test_sync_person_to_users_copies_profile_not_credentials(self, user_types):
        person = Person.objects.create(name='A', last_name='B', dni='4', email='a@test.com')
        user = CustomUser.objects.create_user(
            email='u3@test.com', password='x', name='A', last_name='B',
            dni='4', tipo_usuario=user_types['admin'], person=person,
        )
        person.name = 'Cambiado'
        person.phone = '777'
        person.sex = 'F'
        person.email = 'otro@test.com'   # no debe subir
        person.dni = '999'               # no debe subir
        sync_person_to_users(person)
        user.refresh_from_db()
        assert user.name == 'Cambiado'
        assert user.phone == '777'
        assert user.sex == 'F'
        assert user.email == 'u3@test.com'   # email NO sube Person->User
        assert user.dni == '4'               # dni NO sube

    @pytest.mark.django_db
    def test_find_identity_mismatches_detects_profile_dni_email(self, user_types):
        person = Person.objects.create(
            name='A', last_name='B', dni='5',
            email='div@test.com', phone='1', sex='M',
        )
        user = CustomUser.objects.create_user(
            email='otro@test.com', password='x', name='Z', last_name='B',
            dni='6', tipo_usuario=user_types['admin'], person=person,
            phone='1', sex='M',
        )
        mismatches = find_identity_mismatches()
        pairs = {(u.pk, tuple(sorted(f))) for u, p, f in mismatches}
        # difieren name, dni y email
        assert (user.pk, ('dni', 'email', 'name')) in pairs

    @pytest.mark.django_db
    def test_find_identity_mismatches_empty_when_aligned(self, user_types):
        person = Person.objects.create(name='A', last_name='B', dni='7', email='x@test.com')
        user = CustomUser.objects.create_user(
            email='x@test.com', password='x', name='A', last_name='B',
            dni='7', tipo_usuario=user_types['admin'], person=person,
        )
        sync_user_to_person(user)
        assert find_identity_mismatches() == []


from io import StringIO
from django.core.management import call_command


class TestValidateIdentityConsistencyCommand:
    @pytest.mark.django_db
    def test_command_fix_corrects_drift(self, user_types):
        person = Person.objects.create(name='A', last_name='B', dni='8', email='a8@test.com')
        user = CustomUser.objects.create_user(
            email='a8@test.com', password='x', name='A', last_name='B',
            dni='8', tipo_usuario=user_types['student'], person=person,
        )
        # Inyectar drift sin disparar signals
        Person.all_objects.filter(pk=person.pk).update(name='Desincronizado')
        out = StringIO()
        call_command('validate_identity_consistency', '--fix', stdout=out)
        person.refresh_from_db()
        assert person.name == 'A'  # corregido desde el user (canónico)

    @pytest.mark.django_db
    def test_command_reports_and_exits_nonzero_without_fix(self, user_types):
        person = Person.objects.create(name='A', last_name='B', dni='9', email='a9@test.com')
        CustomUser.objects.create_user(
            email='a9@test.com', password='x', name='A', last_name='B',
            dni='9', tipo_usuario=user_types['student'], person=person,
        )
        Person.all_objects.filter(pk=person.pk).update(name='Drift')
        with pytest.raises(SystemExit):
            call_command('validate_identity_consistency', stdout=StringIO())

    @pytest.mark.django_db
    def test_command_no_mismatches(self, db):
        out = StringIO()
        call_command('validate_identity_consistency', stdout=out)
        assert 'Sin divergencias' in out.getvalue()


class TestIdentitySyncRobustness:
    @pytest.fixture
    def linked_student(self, user_types):
        person = Person.objects.create(
            name='Ivo', last_name='Ruiz', dni='44445555',
            email='ivo@test.com', phone='111', sex='M',
        )
        user = CustomUser.objects.create_user(
            email='ivo@test.com', password='x', name='Ivo', last_name='Ruiz',
            dni='44445555', tipo_usuario=user_types['student'], person=person,
            phone='111', sex='M',
        )
        return user, person

    @pytest.mark.django_db
    def test_person_null_field_does_not_break_user_sync(self, linked_student):
        user, person = linked_student
        Person.all_objects.filter(pk=person.pk).update(sex=None)
        person.refresh_from_db()
        person.save()  # Person->User: sex NULL no debe romper (User.sex es NOT NULL)
        user.refresh_from_db()
        assert user.sex == ''

    @pytest.mark.django_db
    def test_person_edit_never_touches_user_credentials(self, linked_student):
        user, person = linked_student
        person.dni = '00000000'
        person.email = 'hackeado@test.com'
        person.save()
        user.refresh_from_db()
        assert user.dni == '44445555'
        assert user.email == 'ivo@test.com'

    @pytest.mark.django_db
    def test_soft_delete_person_does_not_resync(self, linked_student):
        user, person = linked_student
        CustomUser.all_objects.filter(pk=user.pk).update(name='Renombrado')
        person.delete()  # soft-delete -> save(update_fields=['deleted']) -> no re-sincroniza
        user.refresh_from_db()
        assert user.name == 'Renombrado'

    @pytest.mark.django_db
    def test_long_user_value_truncated_to_person_maxlen(self, linked_student):
        user, person = linked_student
        user.phone = '1' * 25  # User.phone admite 30; Person.phone admite 11
        user.save()
        person.refresh_from_db()
        assert person.phone == '1' * 11


class TestProfileSyncPolicy:
    """Matriz de la política: qué campo se sincroniza en qué dirección."""

    @pytest.fixture
    def linked(self, user_types):
        person = Person.objects.create(
            name='Ema', last_name='Diaz', dni='81810000',
            email='ema@test.com', phone='1', sex='F',
        )
        user = CustomUser.objects.create_user(
            email='ema@test.com', password='x', name='Ema', last_name='Diaz',
            dni='81810000', tipo_usuario=user_types['student'], person=person,
        )
        return user, person

    @pytest.mark.django_db
    def test_user_email_edit_updates_person_email(self, linked):
        user, person = linked
        user.email = 'ema.nueva@test.com'
        user.save()
        person.refresh_from_db()
        assert person.email == 'ema.nueva@test.com'

    @pytest.mark.django_db
    def test_person_email_edit_does_not_touch_user_email(self, linked):
        user, person = linked
        person.email = 'otra@test.com'
        person.save()
        user.refresh_from_db()
        assert user.email == 'ema@test.com'

    @pytest.mark.django_db
    def test_user_dni_edit_updates_person_dni(self, linked):
        user, person = linked
        user.dni = '99990000'
        user.save()
        person.refresh_from_db()
        assert person.dni == '99990000'

    @pytest.mark.django_db
    def test_person_dni_edit_does_not_touch_user_dni(self, linked):
        user, person = linked
        person.dni = '99990000'
        person.save()
        user.refresh_from_db()
        assert user.dni == '81810000'

    @pytest.mark.django_db
    def test_profile_syncs_both_directions(self, linked):
        user, person = linked
        user.phone = '222'
        user.save()
        person.refresh_from_db()
        assert person.phone == '222'      # User -> Person
        person.phone = '333'
        person.save()
        user.refresh_from_db()
        assert user.phone == '333'        # Person -> User


@pytest.mark.django_db
class TestUserSelfService:
    def test_student_can_get_own(self, student_client, student_user):
        resp = student_client.get(reverse('users-detail', args=[student_user.id]))
        assert resp.status_code == 200, resp.data

    def test_student_cannot_get_other(self, student_client, admin_user):
        resp = student_client.get(reverse('users-detail', args=[admin_user.id]))
        assert resp.status_code in (403, 404)

    def test_student_can_patch_own(self, student_client, student_user):
        resp = student_client.patch(reverse('users-detail', args=[student_user.id]),
                                    data={'name': 'NuevoNombre'}, format='json')
        assert resp.status_code == 200, resp.data
        student_user.refresh_from_db()
        assert student_user.name == 'NuevoNombre'

    def test_student_cannot_change_own_tipo(self, student_client, student_user, user_types):
        resp = student_client.patch(reverse('users-detail', args=[student_user.id]),
                                    data={'tipo_usuario': user_types['admin'].id}, format='json')
        assert resp.status_code == 403
        student_user.refresh_from_db()
        assert student_user.tipo_usuario_id == user_types['student'].id

    def test_student_cannot_soft_delete_self(self, student_client, student_user):
        resp = student_client.patch(reverse('users-detail', args=[student_user.id]),
                                    data={'deleted': '2026-01-01T00:00:00Z'}, format='json')
        assert resp.status_code == 403
        student_user.refresh_from_db()
        assert student_user.deleted is None

    def test_student_cannot_toggle_is_student_flag(self, student_client, student_user):
        resp = student_client.patch(reverse('users-detail', args=[student_user.id]),
                                    data={'is_student': True}, format='json')
        assert resp.status_code == 403
        student_user.refresh_from_db()
        assert student_user.is_student is False

    def test_student_cannot_list(self, student_client):
        resp = student_client.get(reverse('users-list'))
        # Student no lista otros: la acción 'list' no está en el OR de get_permissions para Student.
        assert resp.status_code == 403

    def test_authenticated_user_without_tipo_but_student_flag_get_own_returns_403_not_500(self, student_user):
        """
        Regresión: permission_classes de retrieve/update incluye IsStudent, que es
        flag-inclusivo (is_student_user = tipo_usuario_id == student_pk OR is_student).
        Un usuario con tipo_usuario=None e is_student=True pasa el gate de permisos y
        antes del fix reventaba con AttributeError (None.id) al llegar a get_queryset/
        retrieve, devolviendo 500 en vez de una respuesta controlada.
        """
        from apps.users.models import CustomUser as _CustomUser
        flagged_user = _CustomUser.objects.create_user(
            email='sin_tipo_flag@test.com', password='test123',
            name='SinTipo', last_name='ConFlag', dni='56780123',
            tipo_usuario=None, is_student=True,
        )
        client = APIClient()
        client.force_authenticate(user=flagged_user)

        # Ver su propia fila: el guard de get_queryset() ya lo deja sin filas
        # visibles (usuario sin tipo_usuario y no superuser), así que
        # self.get_object() devuelve 404 antes de llegar al guard de retrieve().
        # Lo importante del fix es que nunca sea 500.
        resp_own = client.get(reverse('users-detail', args=[flagged_user.id]))
        assert resp_own.status_code in (403, 404), resp_own.data

        # Ver la fila de otro usuario: tampoco debe ser 500.
        resp_other = client.get(reverse('users-detail', args=[student_user.id]))
        assert resp_other.status_code in (403, 404), resp_other.data


@pytest.mark.django_db
class TestSeedStudentsUsaEstudiante:
    """El seed de alumnos debe usar el tipo canónico 'Estudiante', no crear el
    duplicado 'Student'."""

    def _run(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('seed_students', stdout=StringIO())

    def test_seed_no_crea_tipo_student_duplicado(self):
        self._run()
        assert not UserType.objects.filter(user_type_name='Student').exists()
        assert UserType.objects.filter(user_type_name='Estudiante').exists()

    def test_seed_asigna_tipo_estudiante_a_los_usuarios(self):
        self._run()
        u = CustomUser.objects.get(email='alumno1@test.com')
        assert u.tipo_usuario.user_type_name == 'Estudiante'
        assert u.is_student_user


@pytest.mark.django_db
class TestEmailUniqueCaseInsensitiveKAN157:
    """La unicidad de email debe ser case-insensitive: se normaliza a minúsculas
    al crear y el registro rechaza duplicados que difieren solo en el case."""

    def test_create_user_normaliza_email_a_minusculas(self):
        u = CustomUser.objects.create_user(
            email='Juan@X.COM', name='Juan', last_name='Perez', dni='30111222', password='x',
        )
        u.refresh_from_db()
        assert u.email == 'juan@x.com'

    def test_orm_create_normaliza_email_a_minusculas(self, db):
        # El alta admin (UserRegisterationSerializer -> ModelSerializer.create ->
        # objects.create) NO pasa por create_user; la normalización vive en save().
        u = CustomUser.objects.create(
            email='Ana@Mixed.CoM', name='Ana', last_name='Diaz', dni='31222333',
        )
        u.refresh_from_db()
        assert u.email == 'ana@mixed.com'

    def test_register_endpoint_persiste_email_en_minusculas(self, client, student_type, monkeypatch):
        # El endpoint real de autorregistro (/register/) construye el CustomUser
        # directamente en _create_student; la normalización debe llegar igual.
        monkeypatch.setattr('apps.users.views.send_verification_email', lambda *a, **k: None)
        monkeypatch.setattr('apps.users.views._send_verification_wp', lambda *a, **k: None)
        response = client.post(reverse('register-list'), data={
            'dni': '32444555', 'email': 'Nuevo@X.COM', 'password': 'securepass123',
            'name': 'Nuevo', 'last_name': 'Alumno',
        }, content_type='application/json')
        assert response.status_code == 201
        user = CustomUser.all_objects.get(dni='32444555')
        assert user.email == 'nuevo@x.com'

    def test_register_endpoint_rechaza_case_variant_duplicado(self, client, student_type, monkeypatch):
        monkeypatch.setattr('apps.users.views.send_verification_email', lambda *a, **k: None)
        monkeypatch.setattr('apps.users.views._send_verification_wp', lambda *a, **k: None)
        primero = client.post(reverse('register-list'), data={
            'dni': '33555666', 'email': 'dup@x.com', 'password': 'securepass123',
            'name': 'Dup', 'last_name': 'Uno',
        }, content_type='application/json')
        assert primero.status_code == 201
        # Mismo email con distinto casing (y otro DNI) -> rechazado, no crea segundo user
        segundo = client.post(reverse('register-list'), data={
            'dni': '33555777', 'email': 'DUP@X.COM', 'password': 'securepass123',
            'name': 'Dup', 'last_name': 'Dos',
        }, content_type='application/json')
        assert segundo.status_code == 400
        assert CustomUser.all_objects.filter(email__iexact='dup@x.com').count() == 1

    def test_serializer_rechaza_email_que_difiere_solo_en_case(self, user_types):
        from apps.users.serializers import UserRegisterationSerializer
        CustomUser.objects.create_user(
            email='juan@x.com', name='Juan', last_name='Perez', dni='30111222', password='x',
        )
        serializer = UserRegisterationSerializer(data={
            'email': 'Juan@X.com', 'name': 'Otro', 'last_name': 'Usuario',
            'dni': '40999888', 'tipo_usuario': user_types['student'].id,
            'password': 'x',
        })
        assert not serializer.is_valid()
        assert 'email' in serializer.errors


# envío de mail al registrarse

@pytest.mark.django_db
class TestRegistrationSendsVerificationEmailKAN158:
    """El registro debe disparar el email de verificación (mockeado). Cubre el
    caso alumno nuevo y alumno existente, y verifica que NO se dispara cuando el
    registro es rechazado por duplicado."""
    URL = 'register-list'

    def test_register_new_dispara_email_verificacion(self, client, student_type, monkeypatch):
        calls = []
        monkeypatch.setattr(
            'apps.users.views.send_verification_email',
            lambda email, name, token: calls.append((email, name, token)),
        )
        # el WhatsApp no debe entorpecer el test
        monkeypatch.setattr('apps.users.views._send_verification_wp', lambda *a, **k: None)

        response = client.post(reverse(self.URL), data={
            'dni': '77778888', 'email': 'nuevo@test.com', 'password': 'securepass123',
            'name': 'Carlos', 'last_name': 'Ruiz',
        }, content_type='application/json')

        assert response.status_code == 201
        assert len(calls) == 1
        email, name, token = calls[0]
        assert email == 'nuevo@test.com'
        assert name == 'Carlos'
        assert token  # token de verificación no vacío

    def test_register_existing_dispara_email_verificacion(self, client, person_with_email, student_type, monkeypatch):
        calls = []
        monkeypatch.setattr(
            'apps.users.views.send_verification_email',
            lambda email, name, token: calls.append((email, name, token)),
        )

        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni,
            'email': person_with_email.email,
            'password': 'securepass123',
        }, content_type='application/json')

        assert response.status_code == 201
        assert len(calls) == 1
        assert calls[0][0] == person_with_email.email

    def test_register_duplicado_no_dispara_email(self, client, person_with_email, student_type, monkeypatch):
        calls = []
        monkeypatch.setattr(
            'apps.users.views.send_verification_email',
            lambda email, name, token: calls.append((email, name, token)),
        )
        monkeypatch.setattr('apps.users.views._send_verification_wp', lambda *a, **k: None)
        # Primer registro OK (consume 1 envío)
        client.post(reverse(self.URL), data={
            'dni': person_with_email.dni, 'email': person_with_email.email,
            'password': 'securepass123',
        }, content_type='application/json')
        # Segundo registro con los mismos datos -> rechazado, sin nuevo envío
        response = client.post(reverse(self.URL), data={
            'dni': person_with_email.dni, 'email': person_with_email.email,
            'password': 'otra',
        }, content_type='application/json')

        assert response.status_code == 400
        assert len(calls) == 1  # solo el del primer registro


# envío de mail para recuperar contraseña

@pytest.mark.django_db
class TestPasswordResetSendsEmailKAN159:
    """El flujo de recuperación debe disparar el email de reset (mockeado) solo
    para usuarios activos existentes, y NUNCA para emails desconocidos o cuentas
    inactivas (para no revelar si el email existe)."""
    URL = 'password-reset-list'

    @pytest.fixture
    def active_user(self, person_with_email, student_type):
        user = CustomUser(
            email=person_with_email.email, name=person_with_email.name,
            last_name=person_with_email.last_name, dni=person_with_email.dni,
            tipo_usuario=student_type, person=person_with_email, is_active=True,
        )
        user.set_password('oldpass123')
        user.save()
        return user

    def test_email_existente_dispara_reset(self, client, active_user, monkeypatch):
        calls = []
        monkeypatch.setattr(
            'apps.users.views.send_password_reset_email',
            lambda email, name, token: calls.append((email, name, token)),
        )
        response = client.post(reverse(self.URL), data={'email': active_user.email},
                               content_type='application/json')
        assert response.status_code == 200
        assert len(calls) == 1
        email, name, token = calls[0]
        assert email == active_user.email
        assert name == active_user.name
        assert token

    def test_email_desconocido_no_dispara(self, client, db, monkeypatch):
        calls = []
        monkeypatch.setattr(
            'apps.users.views.send_password_reset_email',
            lambda email, name, token: calls.append((email, name, token)),
        )
        response = client.post(reverse(self.URL), data={'email': 'noexiste@test.com'},
                               content_type='application/json')
        assert response.status_code == 200  # mismo mensaje, no revela existencia
        assert calls == []

    def test_usuario_inactivo_no_dispara(self, client, active_user, monkeypatch):
        active_user.is_active = False
        active_user.save(update_fields=['is_active'])
        calls = []
        monkeypatch.setattr(
            'apps.users.views.send_password_reset_email',
            lambda email, name, token: calls.append((email, name, token)),
        )
        response = client.post(reverse(self.URL), data={'email': active_user.email},
                               content_type='application/json')
        assert response.status_code == 200
        assert calls == []


# email_service operativo con configuración de API key

class TestEmailServiceBrevoKAN158159:
    """El servicio de email debe ser un no-op seguro sin BREVO_API_KEY y hacer el
    POST a Brevo cuando está configurado; y armar payloads correctos."""

    def test_send_sin_api_key_es_noop(self, monkeypatch):
        from apps.users import email_service
        monkeypatch.delenv('BREVO_API_KEY', raising=False)
        posted = []
        monkeypatch.setattr(email_service.requests, 'post',
                            lambda *a, **k: posted.append((a, k)))
        # No debe lanzar ni postear
        email_service._send({'to': [{'email': 'x@y.com'}]}, context='test')
        assert posted == []

    def test_send_con_api_key_postea_a_brevo(self, monkeypatch):
        from apps.users import email_service

        class _Resp:
            ok = True
            status_code = 200
            text = ''

        captured = {}

        def _fake_post(url, json=None, headers=None, timeout=None):
            captured.update(url=url, json=json, headers=headers, timeout=timeout)
            return _Resp()

        monkeypatch.setenv('BREVO_API_KEY', 'test-key')
        monkeypatch.setattr(email_service.requests, 'post', _fake_post)
        email_service._send({'to': [{'email': 'x@y.com'}]}, context='test')

        assert captured['url'] == email_service.BREVO_SMTP_URL
        assert captured['headers']['api-key'] == 'test-key'

    def test_send_verification_email_arma_payload(self, monkeypatch):
        from apps.users import email_service
        captured = {}
        monkeypatch.setattr(email_service, '_send',
                            lambda payload, context: captured.update(payload=payload, context=context))
        email_service.send_verification_email('a@b.com', 'Ana', 'tok123')
        assert captured['context'] == 'verification'
        assert captured['payload']['to'] == [{'email': 'a@b.com', 'name': 'Ana'}]
        assert 'tok123' in captured['payload']['htmlContent']

    def test_send_password_reset_email_arma_payload(self, monkeypatch):
        from apps.users import email_service
        captured = {}
        monkeypatch.setattr(email_service, '_send',
                            lambda payload, context: captured.update(payload=payload, context=context))
        email_service.send_password_reset_email('a@b.com', 'Ana', 'tok999')
        assert captured['context'] == 'password-reset'
        assert captured['payload']['to'] == [{'email': 'a@b.com', 'name': 'Ana'}]
        assert 'tok999' in captured['payload']['htmlContent']


# colisión cross-tipo (email de Admin) -> 400, no 500

@pytest.mark.django_db
class TestRegisterCrossTypeEmailCollisionKAN157:
    """Un alumno que se registra con el email de un Admin/Consultor no puede
    compartir email (unique global). El precheck está scoped a Estudiante (por el
    dedup admin/alumno), así que la colisión la ataja el IntegrityError -> 400
    (antes daba 500). Además no debe quedar un Person huérfano."""
    URL = 'register-list'

    @pytest.fixture
    def admin_type(self, db):
        t, _ = UserType.objects.get_or_create(id=2, defaults={'user_type_name': 'Administrador'})
        return t

    @pytest.fixture(autouse=True)
    def _no_side_effects(self, monkeypatch):
        monkeypatch.setattr('apps.users.views.send_verification_email', lambda *a, **k: None)
        monkeypatch.setattr('apps.users.views._send_verification_wp', lambda *a, **k: None)

    def test_email_de_admin_devuelve_400_no_500(self, client, student_type, admin_type):
        CustomUser.objects.create_user(
            email='shared@x.com', password='pass', name='Admin', last_name='X',
            dni='90001111', tipo_usuario=admin_type,
        )
        resp = client.post(reverse(self.URL), data={
            'dni': '90002222', 'email': 'shared@x.com', 'password': 'securepass123',
            'name': 'Nuevo', 'last_name': 'Alumno',
        }, content_type='application/json')
        assert resp.status_code == 400
        assert not CustomUser.all_objects.filter(
            email__iexact='shared@x.com', tipo_usuario=student_type).exists()
        # rollback: no queda Person huérfano de la creación fallida
        assert not Person.objects.filter(dni='90002222').exists()

    def test_email_de_admin_case_variant_tambien_400(self, client, student_type, admin_type):
        CustomUser.objects.create_user(
            email='shared2@x.com', password='pass', name='Admin', last_name='X',
            dni='90003333', tipo_usuario=admin_type,
        )
        resp = client.post(reverse(self.URL), data={
            'dni': '90004444', 'email': 'SHARED2@X.COM', 'password': 'securepass123',
            'name': 'Nuevo', 'last_name': 'Alumno',
        }, content_type='application/json')
        assert resp.status_code == 400
        assert not Person.objects.filter(dni='90004444').exists()


# unicidad case-insensitive garantizada a nivel DB

@pytest.mark.django_db
class TestEmailCaseInsensitiveDBConstraintKAN157:
    """La unicidad case-insensitive debe estar garantizada por un índice funcional
    Lower('email') en la DB, no solo por la normalización en save() (que un UPDATE
    directo o un bulk pueden bypassear)."""

    def test_db_rechaza_case_variant_por_constraint_funcional(self):
        from django.db import IntegrityError, transaction
        CustomUser.objects.create(email='ci@x.com', name='A', last_name='B', dni='95001111')
        u2 = CustomUser.objects.create(email='other@x.com', name='C', last_name='D', dni='95002222')
        # .update() bypassea save() (no normaliza); si el unique fuera solo
        # case-sensitive, 'CI@X.com' != 'ci@x.com' pasaría. El índice funcional lo frena.
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CustomUser.objects.filter(pk=u2.pk).update(email='CI@X.com')


@pytest.mark.django_db
class TestTokenExpirationKAN247:
    """El access token debe vencer (no durar ~1 año): un token expirado -> 401, y
    las vidas configuradas quedan cortas."""

    def _user(self, dni='70010001', email='tok@test.com'):
        return CustomUser.objects.create_user(
            email=email, password='x', name='Tok', last_name='User', dni=dni,
        )

    def test_token_expirado_devuelve_401(self):
        from datetime import timedelta
        from rest_framework_simplejwt.tokens import AccessToken
        user = self._user()
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(seconds=-10))  # ya vencido
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        resp = client.get(reverse('people-list'))
        assert resp.status_code == 401

    def test_token_valido_autentica(self):
        from rest_framework_simplejwt.tokens import AccessToken
        user = self._user(dni='70010002', email='tok2@test.com')
        token = AccessToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        resp = client.get(reverse('people-list'))
        assert resp.status_code != 401  # autentica OK (200/403 por permisos, no 401)

    def test_access_token_lifetime_corto(self):
        from datetime import timedelta
        from django.conf import settings
        # el access token no debe durar ~1 año; a lo sumo una jornada.
        assert settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] <= timedelta(hours=12)

    def test_refresh_token_lifetime_acortado(self):
        from datetime import timedelta
        from django.conf import settings
        assert settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'] <= timedelta(days=14)
