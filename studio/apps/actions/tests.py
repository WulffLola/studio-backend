import pytest
from datetime import date, time
from django.urls import reverse

from apps.actions.views import resolve_actions_range


class TestResolveActionsRangeKAN150:
    """Helper puro que resuelve el rango de fechas de /actions/."""

    def test_default_ultimos_30_dias(self):
        today = date(2026, 3, 15)
        start_dt, end_dt = resolve_actions_range(None, None, today)
        assert start_dt.date() == date(2026, 2, 13)   # today - 30 días
        assert end_dt.date() == today
        assert start_dt.time() == time.min
        assert end_dt.time() == time.max
        assert start_dt.tzinfo is not None and end_dt.tzinfo is not None  # aware

    def test_rango_explicito(self):
        start_dt, end_dt = resolve_actions_range('2026-01-01', '2026-01-31', date(2026, 3, 15))
        assert start_dt.date() == date(2026, 1, 1)
        assert end_dt.date() == date(2026, 1, 31)
        assert start_dt.time() == time.min and end_dt.time() == time.max

    def test_from_mayor_que_to_lanza_error(self):
        with pytest.raises(ValueError):
            resolve_actions_range('2026-02-01', '2026-01-01', date(2026, 3, 15))

    def test_formato_invalido_lanza_error(self):
        with pytest.raises(ValueError):
            resolve_actions_range('01-01-2026', '2026-01-31', date(2026, 3, 15))

    def test_fecha_imposible_lanza_error(self):
        with pytest.raises(ValueError):
            resolve_actions_range('2026-02-30', '2026-03-01', date(2026, 3, 15))

    def test_solo_date_from_lanza_error(self):
        with pytest.raises(ValueError):
            resolve_actions_range('2026-01-01', None, date(2026, 3, 15))

    def test_solo_date_to_lanza_error(self):
        with pytest.raises(ValueError):
            resolve_actions_range(None, '2026-01-31', date(2026, 3, 15))


@pytest.mark.django_db
class TestActionsEndpointKAN150:
    """/actions/ aplica el default de 30 días y valida el rango.
    Nota: no se crean filas Action (ArrayField rompe en sqlite); se cubren los
    200 sin filas, los 400 de validación y que el filtro NO aplica al detalle."""
    URL = 'actions-list'

    def test_sin_params_devuelve_200(self, admin_client):
        assert admin_client.get(reverse(self.URL)).status_code == 200

    def test_rango_valido_devuelve_200(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-01-01', 'date_to': '2026-01-31'})
        assert resp.status_code == 200

    def test_formato_invalido_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': 'bad', 'date_to': '2026-01-31'})
        assert resp.status_code == 400
        assert isinstance(resp.data.get('detail'), str)  # shape {"detail": "<string>"}

    def test_solo_date_from_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-01-01'})
        assert resp.status_code == 400

    def test_solo_date_to_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_to': '2026-01-31'})
        assert resp.status_code == 400

    def test_from_mayor_que_to_devuelve_400(self, admin_client):
        resp = admin_client.get(reverse(self.URL), {'date_from': '2026-02-01', 'date_to': '2026-01-01'})
        assert resp.status_code == 400

    def test_detalle_ignora_filtro_de_fechas(self, admin_client):
        # El filtro es solo de list: el detalle no debe caer en 400 por date params
        # (una acción inexistente da 404, no 400). fix review)
        url = reverse('actions-detail', args=[999999])
        resp = admin_client.get(url, {'date_from': 'bad'})
        assert resp.status_code == 404
