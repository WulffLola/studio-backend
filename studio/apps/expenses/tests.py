import pytest
from django.urls import reverse
from .models import Expense
from apps.expense_type.models import ExpenseType

@pytest.mark.django_db
class TestExpenseSoftDelete:

    def test_delete_sets_deleted(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        expense.refresh_from_db()
        assert expense.deleted is not None

    def test_objects_hides_deleted(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        assert not Expense.objects.filter(pk=expense.pk).exists()

    def test_all_objects_includes_deleted(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        assert Expense.all_objects.filter(pk=expense.pk).exists()

    def test_all_objects_dead_returns_deleted(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        assert Expense.all_objects.dead().filter(pk=expense.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        assert not Expense.all_objects.alive().filter(pk=expense.pk).exists()

    def test_for_user_admin_sees_deleted(self, studio, admin_user):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        qs = Expense.all_objects.for_user(admin_user)
        assert qs.filter(pk=expense.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, studio, consultor_user):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        qs = Expense.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=expense.pk).exists()

    def test_restore(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        expense.restore()
        expense.refresh_from_db()
        assert expense.deleted is None

    def test_hard_delete_removes_from_db(self, studio):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        pk = expense.pk
        expense.hard_delete()
        assert not Expense.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestExpenseViewForUser:
    URL = 'expenses-list'

    def test_admin_list_includes_deleted(self, studio, admin_client):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert expense.id in ids

    def test_consultor_list_excludes_deleted(self, studio, consultor_client):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        expense.delete()
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert expense.id not in ids

    def test_delete_endpoint_is_soft_delete(self, studio, admin_client):
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='100', type=expense_type, studio=studio)
        url = reverse('expenses-detail', args=[expense.pk])
        response = admin_client.delete(url, data={'code': 'admin'}, format='json')
        if response.status_code != 204:
            print(f"DEBUG: {response.data}")
        assert response.status_code == 204
        assert Expense.all_objects.filter(pk=expense.pk).exists()
        expense.refresh_from_db()
        assert expense.deleted is not None

    def test_create_expense_sueldo_success(self, studio, admin_client, teacher):
        from apps.teachers_hours.models import Hour
        from datetime import datetime
        
        expense_type = ExpenseType.objects.create(name='Sueldo Profesora')
        month = int(datetime.now().strftime('%m'))
        hour = Hour.objects.create(teacher=teacher, month=month, left='5000')
        
        url = reverse(self.URL)
        data = {
            'type_id': expense_type.id,
            'teacher': teacher.id,
            'amount': '1000',
            'studio': studio.id,
            'method': 'Efectivo',
            'date': datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 201
        
        teacher.refresh_from_db()
        assert teacher.last_payment is not None
        
        hour.refresh_from_db()
        assert float(hour.left) == 4000.0
        
        expense = Expense.objects.get(pk=response.data['id'])
        assert f"Pago a {teacher.name}" in expense.observation

    def test_create_expense_gastos_chicos_success(self, studio, admin_client, monkeypatch):
        from apps.actions.models import Action
        from datetime import datetime
        monkeypatch.setattr(Action.objects, "create", lambda **kwargs: None)
        # Mock filter().update() to do nothing
        class MockQS:
            def update(self, **kwargs): return 0
        monkeypatch.setattr(Action.objects, "filter", lambda **kwargs: MockQS())
        
        expense_type = ExpenseType.objects.create(name='Gastos Chicos')
        
        url = reverse(self.URL)
        data = {
            'type_id': expense_type.id,
            'amount': '500',
            'studio': studio.id,
            'method': 'Caja Chica',
            'code': 'admin',
            'date': datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        response = admin_client.post(url, data=data, format='json')
        if response.status_code != 201:
            print(f"DEBUG Gastos Chicos: {response.data}")
        assert response.status_code == 201
        assert Expense.objects.filter(amount='500', type=expense_type).exists()

    def test_consultor_can_delete_expense(self, studio, consultor_client, consultor_user):
        """El consultor puede eliminar gastos ingresando su código personal."""
        consultor_user.code = '4321'
        consultor_user.save(update_fields=['code'])
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='200', type=expense_type, studio=studio)
        url = reverse('expenses-detail', args=[expense.pk])
        response = consultor_client.delete(url, data={'code': '4321'}, format='json')
        assert response.status_code == 204
        expense.refresh_from_db()
        assert expense.deleted is not None

    def test_consultor_no_puede_usar_atajo_admin(self, studio, consultor_client):
        """El atajo code='admin' es solo para Administrador y Super."""
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='200', type=expense_type, studio=studio)
        url = reverse('expenses-detail', args=[expense.pk])
        response = consultor_client.delete(url, data={'code': 'admin'}, format='json')
        assert response.status_code == 403
        expense.refresh_from_db()
        assert expense.deleted is None

    def test_anonymous_cannot_delete_expense(self, studio):
        """Un usuario anónimo no puede eliminar gastos."""
        from rest_framework.test import APIClient
        expense_type = ExpenseType.objects.create(name='Test Type')
        expense = Expense.objects.create(amount='200', type=expense_type, studio=studio)
        url = reverse('expenses-detail', args=[expense.pk])
        response = APIClient().delete(url, data={'code': 'admin'}, format='json')
        assert response.status_code in (401, 403)

    def test_create_expense_sueldo_insufficient_hours(self, studio, admin_client, teacher):
        from apps.teachers_hours.models import Hour
        from datetime import datetime
        
        expense_type = ExpenseType.objects.create(name='Sueldo Profesora')
        month = int(datetime.now().strftime('%m'))
        hour = Hour.objects.create(teacher=teacher, month=month, left='500')
        
        url = reverse(self.URL)
        data = {
            'type_id': expense_type.id,
            'teacher': teacher.id,
            'amount': '1000',
            'studio': studio.id,
            'method': 'Efectivo',
            'date': datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        response = admin_client.post(url, data=data, format='json')
        assert response.status_code == 400
        assert "monto excede las horas disponibles" in response.data['detail']


# filtro opcional por estudio en /expenses/

MSG_400 = "El parámetro 'studio' debe ser un número entero positivo."


@pytest.mark.django_db
class TestExpensesStudioFilterKAN143:
    URL = 'expenses-list'

    @pytest.fixture
    def data(self, studio, studio_b):
        t = ExpenseType.objects.create(name='Luz')
        a1 = Expense.objects.create(amount='100', type=t, method='Efectivo', studio=studio)
        a2 = Expense.objects.create(amount='200', type=t, method='Efectivo', studio=studio)
        b1 = Expense.objects.create(amount='300', type=t, method='Transferencia', studio=studio_b)
        return {'a': {a1.id, a2.id}, 'b': {b1.id}}

    def _ids(self, response):
        return {e['id'] for e in response.data}

    def test_sin_filtro_devuelve_todos(self, admin_client, data):
        r = admin_client.get(reverse(self.URL))
        assert r.status_code == 200
        assert self._ids(r) == data['a'] | data['b']

    def test_filtra_estudio_a(self, admin_client, data, studio):
        r = admin_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert self._ids(r) == data['a']

    def test_filtra_estudio_b(self, admin_client, data, studio_b):
        r = admin_client.get(reverse(self.URL), {'studio': studio_b.id})
        assert r.status_code == 200
        assert self._ids(r) == data['b']

    def test_varios_estudios_coma(self, admin_client, data, studio, studio_b):
        r = admin_client.get(reverse(self.URL) + f'?studio={studio.id},{studio_b.id}')
        assert r.status_code == 200
        assert self._ids(r) == data['a'] | data['b']

    def test_varios_estudios_repetido(self, admin_client, data, studio, studio_b, empty_studio):
        r = admin_client.get(reverse(self.URL) + f'?studio={studio_b.id}&studio={empty_studio.id}')
        assert r.status_code == 200
        assert self._ids(r) == data['b']

    @pytest.mark.parametrize('value', ['abc', '-1', '', '0', '1,'])
    def test_studio_invalido_400(self, admin_client, data, value):
        r = admin_client.get(reverse(self.URL) + f'?studio={value}')
        assert r.status_code == 400
        assert r.data == {'detail': MSG_400}

    def test_studio_inexistente_404(self, admin_client, data):
        r = admin_client.get(reverse(self.URL), {'studio': 999999})
        assert r.status_code == 404
        assert r.data == {'detail': 'No existe un estudio con id 999999.'}

    def test_usuario_sin_permiso_403(self, no_role_client, data, studio):
        r = no_role_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 403

    def test_usuario_con_permiso_200(self, consultor_client, data, studio):
        r = consultor_client.get(reverse(self.URL), {'studio': studio.id})
        assert r.status_code == 200
        assert self._ids(r) == data['a']

    def test_estudio_sin_datos_200_vacio(self, admin_client, data, empty_studio):
        r = admin_client.get(reverse(self.URL), {'studio': empty_studio.id})
        assert r.status_code == 200
        assert r.data == []

    def test_estudio_dado_de_baja_envuelve_respuesta(self, admin_client, deleted_studio):
        t = ExpenseType.objects.create(name='Alquiler')
        e = Expense.objects.create(amount='50', type=t, method='Efectivo', studio=deleted_studio)
        r = admin_client.get(reverse(self.URL), {'studio': deleted_studio.id})
        assert r.status_code == 200
        assert r.data['detail'] == f'El estudio con id {deleted_studio.id} está dado de baja.'
        assert [x['id'] for x in r.data['results']] == [e.id]


@pytest.mark.django_db
class TestExpensesTodayTeachersFechaLocal:
    """ "hoy" usa la fecha local (BA), no el reloj naive del servidor."""

    def test_usa_fecha_local(self, admin_client, monkeypatch, studio):
        import datetime as dt
        from django.utils import timezone
        # 01:00 UTC del 15 == 22:00 BA del 14
        fixed = dt.datetime(2026, 6, 15, 1, 0, tzinfo=dt.timezone.utc)
        monkeypatch.setattr(timezone, 'now', lambda: fixed)
        chicos = ExpenseType.objects.create(name='Gastos Chicos')
        e = Expense.objects.create(amount='100', type=chicos, studio=studio)  # date auto_now_add == fixed
        response = admin_client.get(reverse('expenses_today_teachers-list'))
        assert response.status_code == 200
        assert [item['id'] for item in response.data] == [e.id]


@pytest.mark.django_db
def test_expense_requires_studio(admin_client, studio):
    t = ExpenseType.objects.create(name='Insumos')
    resp = admin_client.post(reverse('expenses-list'),
        {'amount': '100', 'type_id': t.id, 'method': 'Efectivo'}, format='json')
    assert resp.status_code == 400
    assert 'studio' in resp.data
    resp2 = admin_client.post(reverse('expenses-list'),
        {'amount': '100', 'type_id': t.id, 'method': 'Efectivo', 'studio': studio.id}, format='json')
    assert resp2.status_code in (200, 201)


@pytest.mark.django_db
def test_expense_amount_non_numeric_400(admin_client, studio):
    t = ExpenseType.objects.create(name='Insumos')
    resp = admin_client.post(reverse('expenses-list'),
        {'amount': 'abc', 'type_id': t.id, 'method': 'Efectivo', 'studio': studio.id}, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_gastos_chicos_update_audit_monto_es_str(admin_client, studio, monkeypatch):
    from decimal import Decimal
    from apps.actions.models import Action
    captured = []
    monkeypatch.setattr(Action.objects, "create", lambda **kwargs: captured.append(kwargs))
    t = ExpenseType.objects.create(name='Gastos Chicos')
    e = Expense.objects.create(amount=Decimal('100.50'), type=t, studio=studio, method='Caja Chica')
    resp = admin_client.put(reverse('expenses-detail', args=[e.id]),
        {'amount': '250.25', 'type_id': t.id, 'method': 'Caja Chica', 'studio': studio.id, 'code': 'admin'},
        format='json')
    assert resp.status_code == 200, resp.data
    assert len(captured) == 1
    for key, expected in (('old_value', '100.50'), ('new_value', '250.25')):
        monto = [x for x in captured[0][key] if x['field'] == 'Monto'][0]['value']
        assert isinstance(monto, str) and not isinstance(monto, Decimal)
        assert Decimal(monto) == Decimal(expected)


@pytest.mark.django_db
def test_expense_amount_cero_aceptado(admin_client, studio):
    t = ExpenseType.objects.create(name='Insumos')
    resp = admin_client.post(reverse('expenses-list'),
        {'amount': '0', 'type_id': t.id, 'method': 'Efectivo', 'studio': studio.id}, format='json')
    assert resp.status_code in (200, 201), resp.data


@pytest.mark.django_db
def test_studio_con_expense_no_se_puede_borrar_protect(studio):
    from django.db.models import ProtectedError
    t = ExpenseType.objects.create(name='Insumos')
    Expense.objects.create(amount='10', type=t, studio=studio, method='Efectivo')
    with pytest.raises(ProtectedError):
        studio.hard_delete()
