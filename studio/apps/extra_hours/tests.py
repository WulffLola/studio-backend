import pytest
from datetime import date
from django.urls import reverse
from .models import ExtraHours


@pytest.mark.django_db
class TestExtraHoursSoftDelete:

    def test_delete_sets_deleted(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        eh.refresh_from_db()
        assert eh.deleted is not None

    def test_objects_hides_deleted(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        assert not ExtraHours.objects.filter(pk=eh.pk).exists()

    def test_all_objects_includes_deleted(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        assert ExtraHours.all_objects.filter(pk=eh.pk).exists()

    def test_all_objects_dead_returns_deleted(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        assert ExtraHours.all_objects.dead().filter(pk=eh.pk).exists()

    def test_all_objects_alive_excludes_deleted(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        assert not ExtraHours.all_objects.alive().filter(pk=eh.pk).exists()

    def test_for_user_admin_sees_deleted(self, admin_user, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        qs = ExtraHours.all_objects.for_user(admin_user)
        assert qs.filter(pk=eh.pk).exists()

    def test_for_user_consultor_excludes_deleted(self, consultor_user, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        qs = ExtraHours.all_objects.for_user(consultor_user)
        assert not qs.filter(pk=eh.pk).exists()

    def test_restore(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        eh.delete()
        eh.restore()
        eh.refresh_from_db()
        assert eh.deleted is None

    def test_hard_delete_removes_from_db(self, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=100.0)
        pk = eh.pk
        eh.hard_delete()
        assert not ExtraHours.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestExtraHoursViewForUser:
    URL = 'extra-hours-list'

    def test_admin_list_includes_deleted(self, admin_client, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=200.0)
        eh.delete()
        response = admin_client.get(reverse(self.URL))
        assert response.status_code == 200
        ids = [item['id'] for item in response.data]
        assert eh.id in ids

    def test_consultor_cannot_access(self, consultor_client):
        response = consultor_client.get(reverse(self.URL))
        assert response.status_code == 403

    def test_delete_endpoint_is_soft_delete(self, admin_client, teacher, slot):
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot,
                                       date=date.today(), price=150.0)
        url = reverse('extra-hours-detail', args=[eh.pk])
        response = admin_client.delete(url)
        assert response.status_code == 204
        assert ExtraHours.all_objects.filter(pk=eh.pk).exists()
        eh.refresh_from_db()
        assert eh.deleted is not None


@pytest.mark.django_db
class TestExtraHoursPerDayValidationKAN250:
    """La validación de conflicto de horas extras debe ser POR DÍA + horario
    (mismo profesor, mismo slot__date y slot__start_time), no por slot exacto,
    para que las horas de un día no afecten la validación de otro."""
    URL = 'extra-hours-list'

    def _slot(self, status, room, d, t=None):
        from datetime import time
        from apps.slots.models import Slot
        t = t or time(9, 0)
        return Slot.objects.create(
            status=status, room=room, date=d,
            start_time=t, end_time=time(t.hour + 1, 0), availability=10,
        )

    def _second_room(self, room):
        from apps.rooms.models import Room
        return Room.objects.create(name='Sala 2', studio=room.studio)

    def _hour(self, teacher, d):
        from apps.teachers_hours.models import Hour
        return Hour.objects.create(
            teacher=teacher, month=d.strftime('%m'),
            hour='0', extra_hour='0', total='0', left='0',
        )

    def test_conflicto_mismo_dia_y_horario_distinto_slot_400(self, admin_client, teacher, status, room):
        from datetime import time, timedelta
        from apps.slots.models import Slot
        d = date.today() + timedelta(days=2)
        slot_a = self._slot(status, room, d)
        slot_a2 = Slot.objects.create(
            status=status, room=self._second_room(room), date=d,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )
        ExtraHours.objects.create(teacher=teacher, slot=slot_a, price=0)
        self._hour(teacher, d)  # para que el flujo actual llegue a crear (demuestra el bug)
        resp = admin_client.post(reverse(self.URL), data={
            'teacher_id': teacher.id, 'slot_id': slot_a2.id, 'price': 0,
        }, format='json')
        assert resp.status_code == 400, resp.data
        assert not ExtraHours.objects.filter(slot=slot_a2).exists()

    def test_mismo_horario_otro_dia_ok(self, admin_client, teacher, status, room):
        from datetime import timedelta
        d1 = date.today() + timedelta(days=2)
        d2 = d1 + timedelta(days=7)
        slot_a = self._slot(status, room, d1)
        slot_b = self._slot(status, room, d2)  # mismo horario 9:00, OTRO día
        ExtraHours.objects.create(teacher=teacher, slot=slot_a, price=0)
        self._hour(teacher, d2)
        resp = admin_client.post(reverse(self.URL), data={
            'teacher_id': teacher.id, 'slot_id': slot_b.id, 'price': 0,
        }, format='json')
        assert resp.status_code == 201, resp.data
        assert ExtraHours.objects.filter(slot=slot_b).exists()

    def test_update_hacia_conflicto_400(self, admin_client, teacher, status, room):
        from datetime import time, timedelta
        from apps.slots.models import Slot
        d1 = date.today() + timedelta(days=2)
        d2 = d1 + timedelta(days=7)
        slot_a = self._slot(status, room, d1)
        slot_b = self._slot(status, room, d2)
        slot_a2 = Slot.objects.create(
            status=status, room=self._second_room(room), date=d1,
            start_time=time(9, 0), end_time=time(10, 0), availability=10,
        )
        ExtraHours.objects.create(teacher=teacher, slot=slot_a, price=0)
        eh2 = ExtraHours.objects.create(teacher=teacher, slot=slot_b, price=0)
        resp = admin_client.patch(reverse('extra-hours-detail', args=[eh2.id]), data={
            'teacher_id': teacher.id, 'slot_id': slot_a2.id,
        }, format='json')
        assert resp.status_code == 400, resp.data

    def test_update_a_slot_sin_conflicto_ok(self, admin_client, teacher, status, room):
        from datetime import timedelta
        d1 = date.today() + timedelta(days=2)
        d2 = d1 + timedelta(days=7)
        slot_a = self._slot(status, room, d1)
        slot_b = self._slot(status, room, d2)
        eh = ExtraHours.objects.create(teacher=teacher, slot=slot_a, price=0)
        resp = admin_client.patch(reverse('extra-hours-detail', args=[eh.id]), data={
            'teacher_id': teacher.id, 'slot_id': slot_b.id,
        }, format='json')
        assert resp.status_code == 200, resp.data
