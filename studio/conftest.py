"""
Fixtures compartidos para todos los tests del proyecto.
Los user_types se crean con IDs explícitos para que ADMIN_USER_TYPES = [1, 2]
funcione correctamente en for_user().
"""
import pytest
from datetime import time, date, timedelta
from rest_framework.test import APIClient

from django.utils import timezone
from apps.user_type.models import UserType
from apps.users.models import CustomUser
from apps.studios.models import Studio
from apps.weeks.models import Week
from apps.status.models import Status
from apps.rooms.models import Room
from apps.teachers.models import Teacher
from apps.people.models import Person, PersonActivePlan
from apps.slots.models import Slot
from apps.plans_type.models import PlansType, ComboPlanDiscount
from apps.plans_subtype.models import PlansSubtype
from apps.activity_type.models import ActivityType
from apps.activity_subtype.models import ActivitySubType
from apps.payments.models import Payment, PaymentItem


# Tipos de usuario

@pytest.fixture
def user_types(db):
    """IDs fijos para que for_user() distinga admin (1,2) de no-admin (3+)."""
    super_type     = UserType.objects.create(id=1, user_type_name='Super')
    admin_type     = UserType.objects.create(id=2, user_type_name='Administrador')
    consultor_type = UserType.objects.create(id=3, user_type_name='Consultor')
    student_type   = UserType.objects.create(id=4, user_type_name='Estudiante')
    return {'super': super_type, 'admin': admin_type, 'consultor': consultor_type, 'student': student_type}


# Usuarios

@pytest.fixture
def super_user(user_types):
    return CustomUser.objects.create_user(
        email='super@test.com', password='test123',
        name='Super', last_name='User', dni='12345678',
        tipo_usuario=user_types['super'],
    )


@pytest.fixture
def admin_user(user_types):
    return CustomUser.objects.create_user(
        email='admin@test.com', password='test123',
        name='Admin', last_name='User', dni='23456789',
        tipo_usuario=user_types['admin'],
    )


@pytest.fixture
def consultor_user(user_types):
    return CustomUser.objects.create_user(
        email='consultor@test.com', password='test123',
        name='Consultor', last_name='User', dni='34567890',
        tipo_usuario=user_types['consultor'],
    )


@pytest.fixture
def student_user(user_types):
    return CustomUser.objects.create_user(
        email='student@test.com', password='test123',
        name='Student', last_name='User', dni='45678901',
        tipo_usuario=user_types['student'],
    )


# API clients autenticados

@pytest.fixture
def super_client(super_user):
    client = APIClient()
    client.force_authenticate(user=super_user)
    return client


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def consultor_client(consultor_user):
    client = APIClient()
    client.force_authenticate(user=consultor_user)
    return client


@pytest.fixture
def student_client(student_user):
    client = APIClient()
    client.force_authenticate(user=student_user)
    return client


# Fixtures de modelos compartidos

@pytest.fixture
def studio(db):
    return Studio.objects.create(name='Test Studio')


@pytest.fixture
def week(db):
    # Aún necesario para SlotTemplate.days_of_week (M2M con Week)
    return Week.objects.create(day='Lunes')


@pytest.fixture
def status(db):
    obj, _ = Status.objects.get_or_create(id=1, defaults={'status': 'Disponible'})
    return obj


@pytest.fixture
def room(studio):
    return Room.objects.create(name='Sala 1', studio=studio)


@pytest.fixture
def teacher(db):
    return Teacher.objects.create(name='Ana', last_name='Garcia', dni='11111111')


@pytest.fixture
def person(db):
    return Person.objects.create(name='Juan', last_name='Perez', dni='99999999')


@pytest.fixture
def slot(status, room):
    # week_day eliminado del modelo Slot; ahora se usa date
    return Slot.objects.create(
        status=status,
        room=room,
        date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        availability=10,
    )


@pytest.fixture
def slot_future(status, room):
    """Slot con date >= hoy para tests de /upcoming-appointments/."""
    return Slot.objects.create(
        status=status,
        room=room,
        date=date.today() + timedelta(days=3),
        start_time=time(9, 0),
        end_time=time(10, 0),
        availability=10,
    )


@pytest.fixture
def slot_past(status, room):
    """Slot con date < hoy para tests de /past-appointments/."""
    return Slot.objects.create(
        status=status,
        room=room,
        date=date.today() - timedelta(days=3),
        start_time=time(9, 0),
        end_time=time(10, 0),
        availability=10,
    )


# Fixtures de planes, actividades y combos

@pytest.fixture
def plans_type(db):
    return PlansType.objects.create(name='Danza Clásica')


@pytest.fixture
def plans_type_b(db):
    return PlansType.objects.create(name='Pilates')


@pytest.fixture
def activity_type(db):
    return ActivityType.objects.create(name='Danza')


@pytest.fixture
def activity_subtype(activity_type):
    # plans_type eliminado de ActivitySubType en el refactor
    return ActivitySubType.objects.create(name='Clásica', activity_type=activity_type)


@pytest.fixture
def plans_subtype_a(plans_type, activity_subtype):
    """PlansSubtype con activity_subtype para que EnrollmentCheck funcione."""
    return PlansSubtype.objects.create(
        name='1 día/semana',
        plan_type=plans_type,
        activity_subtype=activity_subtype,
    )


@pytest.fixture
def plans_subtype_b(plans_type_b):
    return PlansSubtype.objects.create(name='2 días/semana', plan_type=plans_type_b)


@pytest.fixture
def combo_plan_discount(plans_subtype_a, plans_subtype_b):
    combo = ComboPlanDiscount.objects.create(discount_pct='10.00')
    combo.plans.set([plans_subtype_a, plans_subtype_b])
    return combo


@pytest.fixture
def plan_discount(plans_subtype_a):
    from apps.plans_type.models import PlanDiscount
    return PlanDiscount.objects.create(plans_subtype=plans_subtype_a, discount_pct='15.00')


@pytest.fixture
def slot_with_activity(status, room, activity_subtype):
    """Slot con activity_subtype para enrollment check y check_plans_availability."""
    return Slot.objects.create(
        status=status,
        room=room,
        date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        availability=10,
        activity_subtype=activity_subtype,
    )


@pytest.fixture
def person_active_plan(person, plans_subtype_a):
    """Plan activo vigente (exp_date futura, sesiones disponibles)."""
    return PersonActivePlan.objects.create(
        person=person,
        plans_subtype=plans_subtype_a,
        exp_date=date.today() + timedelta(days=365),
        sessions_total=10,
        sessions_remaining=10,
    )


@pytest.fixture
def overdue_plan(person, plans_subtype_a):
    """Plan vencido (exp_date pasada) para tests de /overdue-payments/."""
    return PersonActivePlan.objects.create(
        person=person,
        plans_subtype=plans_subtype_a,
        exp_date=date.today() - timedelta(days=10),
        sessions_total=8,
        sessions_remaining=3,
    )


@pytest.fixture
def payment(person, studio):
    return Payment.objects.create(
        person=person,
        studio=studio,
        amount='1000',
        date=timezone.now(),
        method='Efectivo',
    )


@pytest.fixture
def payment_item(payment, plans_subtype_a):
    # plans_type renombrado a plans_subtype en PaymentItem
    return PaymentItem.objects.create(
        payment=payment,
        plans_subtype=plans_subtype_a,
        base_amount='1000.00',
        discount_pct='10.00',
    )


# Fixtures para el filtro por estudio

@pytest.fixture
def studio_b(db):
    return Studio.objects.create(name='Test Studio B')


@pytest.fixture
def empty_studio(db):
    """Estudio existente sin ningún registro asociado."""
    return Studio.objects.create(name='Estudio Vacio')


@pytest.fixture
def deleted_studio(db):
    """Estudio dado de baja (soft-delete): p. ej. un estudio cerrado."""
    s = Studio.objects.create(name='Estudio Cerrado')
    s.delete()
    return s


@pytest.fixture
def room_b(studio_b):
    return Room.objects.create(name='Sala B', studio=studio_b)


@pytest.fixture
def slot_b(status, room_b):
    return Slot.objects.create(
        status=status,
        room=room_b,
        date=date.today() + timedelta(days=1),
        start_time=time(11, 0),
        end_time=time(12, 0),
        availability=10,
    )


@pytest.fixture
def no_role_client(user_types):
    """Usuario autenticado al que se le quitó el rol (sin tipo_usuario ni flag
    de alumno): los permission_classes por rol le deniegan el acceso (403).
    Depende de user_types porque IsAdministrador/IsConsultor/IsSuper comparan
    contra el UserType de la base; sin esos registros None == None daría acceso."""
    user = CustomUser.objects.create_user(
        email='sinrol@test.com', password='test123',
        name='Sin', last_name='Rol', dni='56789012',
        tipo_usuario=None,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client
