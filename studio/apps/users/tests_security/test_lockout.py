"""Bloque 3: bloqueo temporal de login por cuenta e IP."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import Client
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.users.models import AuthLock

PWD = "test123"
LOCK_MSG = "Demasiados intentos fallidos"


def post(url, data, ip="10.0.0.1"):
    return APIClient().post(url, data, format="json", HTTP_X_FORWARDED_FOR=ip)


def fail_login(ident, n, url="/login/", ip="10.0.0.1"):
    rs = []
    for _ in range(n):
        if url == "/token/":
            rs.append(post(url, {"email": ident, "password": "mala"}, ip))
        else:
            rs.append(post(url, {"identifier": ident, "password": "mala"}, ip))
    return rs


@pytest.mark.django_db
class TestAccountLockout:
    def test_five_failures_lock_for_15_minutes(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            rs = fail_login(admin_user.email, 5)
            assert [r.status_code for r in rs] == [400] * 5
            r = post("/login/", {"identifier": admin_user.email, "password": PWD})
            assert r.status_code == 429 and LOCK_MSG in str(r.data["detail"])
            ft.tick(timedelta(minutes=14, seconds=50))
            assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 429
            ft.tick(timedelta(seconds=20))
            assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 200

    def test_four_failures_do_not_lock_and_success_resets(self, admin_user):
        fail_login(admin_user.email, 4)
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 200
        fail_login(admin_user.email, 4)
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 200

    def test_failures_outside_window_do_not_accumulate(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            fail_login(admin_user.email, 4)
            ft.tick(timedelta(minutes=16))
            fail_login(admin_user.email, 4)
            assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 200

    def test_email_and_dni_share_counter(self, admin_user):
        fail_login(admin_user.email, 3)
        fail_login(admin_user.dni, 2)
        assert post("/login/", {"identifier": admin_user.dni, "password": PWD}).status_code == 429
        assert post("/login/", {"identifier": admin_user.email.upper(), "password": PWD}).status_code == 429

    def test_cannot_bypass_by_switching_endpoint(self, student_user):
        fail_login(student_user.email, 2, url="/login/")
        fail_login(student_user.dni, 2, url="/student-login/")
        fail_login(student_user.email, 1, url="/token/")
        for url, data in (("/login/", {"identifier": student_user.email, "password": PWD}),
                          ("/student-login/", {"identifier": student_user.dni, "password": PWD}),
                          ("/token/", {"email": student_user.email, "password": PWD})):
            assert post(url, data).status_code == 429, url
        # /api-auth/login/ (sesión Django) también respeta el bloqueo
        c = Client()
        c.get("/api-auth/login/")
        r = c.post("/api-auth/login/", {"username": student_user.email, "password": PWD})
        assert "_auth_user_id" not in c.session

    def test_api_auth_login_failures_count(self, admin_user):
        c = Client()
        for _ in range(5):
            c.post("/api-auth/login/", {"username": admin_user.email, "password": "mala"},
                   HTTP_X_FORWARDED_FOR="10.0.0.9")
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 429

    def test_lock_applies_from_any_ip(self, admin_user):
        """Ataque distribuido: el bloqueo de la cuenta es global (no por IP)."""
        for i in range(5):
            fail_login(admin_user.email, 1, ip=f"10.0.1.{i}")
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}, ip="10.9.9.9").status_code == 429

    def test_nonexistent_account_same_responses(self, admin_user):
        """Misma respuesta para cuentas existentes e inexistentes (no enumera)."""
        a = fail_login(admin_user.email, 6)
        b = fail_login("noexiste@test.com", 6, ip="10.0.0.2")
        assert [r.status_code for r in a] == [r.status_code for r in b] == [400] * 5 + [429]
        assert a[0].data == b[0].data
        assert a[-1].data == b[-1].data

    def test_inactive_or_deleted_user_generic_error(self, admin_user):
        admin_user.is_active = False
        admin_user.save()
        r = post("/login/", {"identifier": admin_user.email, "password": PWD})
        assert r.status_code == 400 and "Credenciales incorrectas" in str(r.data)

    def test_unlock_command(self, admin_user):
        fail_login(admin_user.email, 5)
        call_command("desbloquear_acceso", admin_user.dni)
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}).status_code == 200


@pytest.mark.django_db
class TestIpLimits:
    def test_ip_locked_after_20_failures_across_accounts(self, admin_user):
        for i in range(4):
            fail_login(f"x{i}@test.com", 5, ip="10.0.0.50")
        # la IP queda bloqueada incluso para una cuenta válida
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}, ip="10.0.0.50").status_code == 429
        # otras IP no se ven afectadas
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}, ip="10.0.0.51").status_code == 200

    def test_attacker_ip_can_lock_at_most_few_accounts(self, user_types):
        from apps.users.models import CustomUser
        victims = [CustomUser.objects.create_user(email=f"v{i}@t.com", password=PWD, name="V",
                                                  last_name="V", dni=f"3000000{i}") for i in range(6)]
        for v in victims:
            fail_login(v.email, 5, ip="10.6.6.6")
        locked = AuthLock.objects.filter(scope="account").count()
        assert locked <= 4

    def test_spoofed_xff_leftmost_ignored(self, admin_user):
        """Con 1 proxy de confianza se usa la IP más a la derecha (la que agrega nginx)."""
        for i in range(20):
            post("/login/", {"identifier": f"z{i}@t.com", "password": "x"}, ip=f"1.2.3.{i}, 10.0.0.77")
        assert post("/login/", {"identifier": admin_user.email, "password": PWD}, ip="5.5.5.5, 10.0.0.77").status_code == 429

    def test_public_endpoints_request_budget(self, db):
        codes = [post("/password-reset/", {"email": f"a{i}@t.com"}, ip="10.0.0.60").status_code for i in range(31)]
        assert codes[:30] == [200] * 30 and codes[30] == 429
        assert post("/register/check/", {"dni": "1", "email": "a@a.com"}, ip="10.0.0.60").status_code == 429
        assert post("/register/check/", {"dni": "1", "email": "a@a.com"}, ip="10.0.0.61").status_code == 200

    def test_verify_email_bad_tokens_count_for_ip(self, db):
        for _ in range(20):
            post("/register/verify-email/", {"token": "malo"}, ip="10.0.0.70")
        assert post("/register/verify-email/", {"token": "malo"}, ip="10.0.0.70").status_code == 429
