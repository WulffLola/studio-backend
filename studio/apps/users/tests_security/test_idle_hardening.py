"""Inactividad de 30 min: el servidor no debe depender del valor que informa el cliente.

Escenarios de abuso: requests manuales / polling sin header, headers manipulados,
refresh de una sesión inactiva y sesiones por cookie (/api-auth/).
"""
from datetime import timedelta

import pytest
from django.test import Client
from freezegun import freeze_time
from rest_framework.test import APIClient

PWD = "test123"


def login(user):
    r = APIClient().post("/login/", {"identifier": user.email, "password": PWD}, format="json")
    assert r.status_code == 200, r.data
    return r.data["tokens"]


def get(access, idle=None, path="/users/"):
    extra = {"HTTP_AUTHORIZATION": f"Bearer {access}"}
    if idle is not None:
        extra["HTTP_X_CLIENT_IDLE"] = str(idle)
    return APIClient().get(path, **extra)


def refresh(tok):
    return APIClient().post("/token/refresh/", {"refresh": tok}, format="json")


@pytest.mark.django_db
class TestServerSideIdle:
    def test_default_requires_activity_header(self, settings):
        from django.conf import settings as s
        assert s.AUTH_ACTIVITY_HEADER_REQUIRED is True

    def test_polling_without_header_does_not_keep_alive(self, admin_user):
        """Requests manuales/automáticos sin X-Client-Idle no cuentan como actividad."""
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            acc, tok = t["access"], t["refresh"]
            for _ in range(3):  # cada 10 min: refresh + request, sin header
                ft.tick(timedelta(minutes=10))
                r = refresh(tok)
                if r.status_code != 200:
                    break
                acc, tok = r.data["access"], r.data["refresh"]
                assert get(acc).status_code == 200
            ft.tick(timedelta(minutes=1))  # 31 min desde la última actividad real (login)
            assert get(acc).status_code == 401
            assert refresh(tok).status_code == 401

    def test_inactive_session_cannot_be_revived_with_idle_zero(self, admin_user):
        """Tras 30 min sin actividad, ni un request 'activo' ni un refresh la reviven."""
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=19))
            r = refresh(t["refresh"]); assert r.status_code == 200
            ft.tick(timedelta(minutes=12))
            assert get(r.data["access"], idle=0).status_code == 401
            assert refresh(r.data["refresh"]).status_code == 401
            # la sesión quedó revocada en el servidor
            from apps.users.models import AuthSession
            assert AuthSession.objects.get().revoke_reason == "idle"

    @pytest.mark.parametrize("bad", ["inf", "-inf", "1e308", "nan", "-1", "", "abc", "99999999999999999999"])
    def test_manipulated_header_never_counts_nor_crashes(self, admin_user, bad):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=15))
            r = refresh(t["refresh"])
            resp = get(r.data["access"], idle=bad)
            assert resp.status_code == 200  # no 500
            ft.tick(timedelta(minutes=16))
            assert refresh(r.data["refresh"]).status_code == 401

    def test_activity_cannot_be_set_in_the_future_or_before_now(self, admin_user):
        from apps.users.models import AuthSession
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=10))
            get(t["access"], idle=0)
            s = AuthSession.objects.get()
            assert s.last_activity_at.isoformat().startswith("2026-11-05T10:10")

    def test_absolute_8h_still_enforced_with_activity(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            acc, tok = t["access"], t["refresh"]
            for _ in range(16):  # 16 × 29 min = 7 h 44 m
                ft.tick(timedelta(minutes=29))
                r = refresh(tok); assert r.status_code == 200
                acc, tok = r.data["access"], r.data["refresh"]
                assert get(acc, idle=1).status_code == 200
            ft.tick(timedelta(minutes=17))  # 8 h 01 m
            assert get(acc, idle=0).status_code == 401
            assert refresh(tok).status_code == 401

    def test_logout_unchanged(self, admin_user):
        t = login(admin_user)
        r = APIClient().post("/logout/", {"refresh_token": t["refresh"]}, format="json",
                             HTTP_AUTHORIZATION=f"Bearer {t['access']}")
        assert r.status_code == 200
        assert get(t["access"], idle=0).status_code == 401
        assert refresh(t["refresh"]).status_code == 401


@pytest.mark.django_db
class TestCookieSessionsAlsoExpire:
    """/api-auth/ (sesión Django por cookie) no puede saltear los límites."""

    def _login(self, user):
        c = Client()
        r = c.post("/api-auth/login/", {"username": user.email, "password": PWD})
        assert "_auth_user_id" in c.session
        return c

    def test_cookie_session_idle_30_min(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            c = self._login(admin_user)
            assert c.get("/users/", HTTP_ACCEPT="application/json").status_code == 200
            ft.tick(timedelta(minutes=20))
            assert c.get("/users/", HTTP_ACCEPT="application/json").status_code == 200  # polling sin header
            ft.tick(timedelta(minutes=11))
            assert c.get("/users/", HTTP_ACCEPT="application/json").status_code in (401, 403)

    def test_cookie_session_activity_header_extends(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            c = self._login(admin_user)
            for _ in range(3):
                ft.tick(timedelta(minutes=20))
                assert c.get("/users/", HTTP_ACCEPT="application/json", HTTP_X_CLIENT_IDLE="0").status_code == 200

    def test_cookie_session_8h(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            c = self._login(admin_user)
            for _ in range(16):
                ft.tick(timedelta(minutes=29))
                assert c.get("/users/", HTTP_ACCEPT="application/json", HTTP_X_CLIENT_IDLE="0").status_code == 200
            ft.tick(timedelta(minutes=17))
            assert c.get("/users/", HTTP_ACCEPT="application/json", HTTP_X_CLIENT_IDLE="0").status_code in (401, 403)
