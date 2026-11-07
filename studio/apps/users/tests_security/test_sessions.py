"""Bloque 2: sesiones JWT (20 min / rotación / 8 h / 30 min inactividad / revocación)."""
from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import AuthSession

PWD = "test123"


def login(user, ident=None, url="/login/"):
    c = APIClient()
    r = c.post(url, {"identifier": ident or user.email, "password": PWD}, format="json")
    assert r.status_code == 200, r.data
    return r.data["tokens"]


def get(path, access, idle=None):
    c = APIClient()
    extra = {"HTTP_AUTHORIZATION": f"Bearer {access}"}
    if idle is not None:
        extra["HTTP_X_CLIENT_IDLE"] = str(idle)
    return c.get(path, **extra)


def refresh(tok):
    return APIClient().post("/token/refresh/", {"refresh": tok}, format="json")


def claims(tok):
    return jwt.decode(tok, options={"verify_signature": False})


@pytest.mark.django_db
class TestLifetimes:
    def test_access_20_min_refresh_capped_8h(self, admin_user):
        with freeze_time("2026-11-05 10:00:00"):
            t = login(admin_user)
        a, r = claims(t["access"]), claims(t["refresh"])
        login_ts = int(timezone.datetime(2026, 11, 5, 10, tzinfo=timezone.utc).timestamp())
        assert a["exp"] - login_ts == 20 * 60
        assert r["exp"] - login_ts == 8 * 3600
        assert a["sid"] == r["sid"] and a["tv"] == 0
        assert "session_expires_at" in t

    def test_access_expires_after_20_min(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            assert get("/users/", t["access"], idle=0).status_code == 200
            ft.tick(timedelta(minutes=21))
            assert get("/users/", t["access"], idle=0).status_code == 401

    def test_legacy_token_without_session_rejected(self, admin_user):
        legacy = RefreshToken.for_user(admin_user)
        assert get("/users/", str(legacy.access_token)).status_code == 401
        assert refresh(str(legacy)).status_code == 401

    def test_all_login_endpoints_issue_session_tokens(self, student_user):
        t1 = login(student_user, url="/student-login/")
        t2 = login(student_user, ident=student_user.dni)
        r = APIClient().post("/token/", {"email": student_user.email, "password": PWD}, format="json")
        assert r.status_code == 200 and {"access", "refresh"} <= set(r.data)
        for tok in (t1["access"], t2["access"], r.data["access"]):
            assert "sid" in claims(tok)
        assert AuthSession.objects.filter(user=student_user).count() == 3


@pytest.mark.django_db
class TestRefreshRotation:
    def test_rotation_and_blacklist(self, admin_user):
        t = login(admin_user)
        r1 = refresh(t["refresh"])
        assert r1.status_code == 200 and r1.data["refresh"] != t["refresh"]
        # el refresh anterior ya no sirve
        assert refresh(t["refresh"]).status_code == 401
        # el nuevo sí
        assert refresh(r1.data["refresh"]).status_code == 200

    def test_concurrent_reuse_within_grace_does_not_kill_session(self, admin_user):
        t = login(admin_user)
        r1 = refresh(t["refresh"])
        assert refresh(t["refresh"]).status_code == 401  # segunda pestaña, misma ventana
        assert get("/users/", r1.data["access"], idle=0).status_code == 200

    def test_reuse_after_grace_revokes_session(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            r1 = refresh(t["refresh"])
            ft.tick(timedelta(minutes=2))
            assert refresh(t["refresh"]).status_code == 401  # reutilización → robo probable
            assert get("/users/", r1.data["access"], idle=0).status_code == 401
            assert refresh(r1.data["refresh"]).status_code == 401

    def test_refresh_never_exceeds_8h(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            tok = t["refresh"]
            for _ in range(15):  # 15 × 29 min = 7 h 15 m, con actividad real
                ft.tick(timedelta(minutes=29))
                acc = refresh(tok)
                assert acc.status_code == 200, acc.data
                tok = acc.data["refresh"]
                assert get("/users/", acc.data["access"], idle=0).status_code == 200
            expires = timezone.now().replace(hour=18, minute=0, second=0)
            assert claims(tok)["exp"] <= int(expires.timestamp())
            assert claims(acc.data["access"])["exp"] <= int(expires.timestamp())
            ft.tick(timedelta(minutes=29))  # 7h44
            acc = refresh(tok); assert acc.status_code == 200
            ft.tick(timedelta(minutes=17))  # 8h01
            assert refresh(acc.data["refresh"]).status_code == 401
            assert get("/users/", acc.data["access"], idle=0).status_code == 401


@pytest.mark.django_db
class TestInactivity:
    def test_idle_30_min_without_activity_expires(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=19))
            assert get("/users/", t["access"], idle=19 * 60).status_code == 200  # polling: no extiende
            ft.tick(timedelta(minutes=12))  # 31 min sin actividad real
            r = refresh(t["refresh"])
            assert r.status_code == 401

    def test_refresh_does_not_count_as_activity(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            tok = t["refresh"]
            for _ in range(3):  # refresca cada 10 min sin actividad
                ft.tick(timedelta(minutes=10))
                r = refresh(tok)
                if r.status_code != 200:
                    break
                tok = r.data["refresh"]
            ft.tick(timedelta(minutes=1))
            assert refresh(tok).status_code == 401

    def test_polling_with_idle_header_does_not_keep_alive(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            acc = t["access"]
            for m in (5, 10, 15):
                ft.tick(timedelta(minutes=5))
                assert get("/users/", acc, idle=m * 60).status_code == 200
            ft.tick(timedelta(minutes=4))
            r = refresh(t["refresh"]); assert r.status_code == 200
            ft.tick(timedelta(minutes=12))  # 31 min desde el login, sin actividad real
            assert get("/users/", r.data["access"], idle=31 * 60).status_code == 401

    def test_real_activity_keeps_session(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            acc, tok = t["access"], t["refresh"]
            for _ in range(4):  # 4 × 18 min = 72 min, con interacción
                ft.tick(timedelta(minutes=18))
                r = refresh(tok); assert r.status_code == 200
                acc, tok = r.data["access"], r.data["refresh"]
                assert get("/session/", acc, idle=5).status_code == 200

    def test_activity_is_checked_before_update(self, admin_user):
        """Una petición con 'actividad' no revive una sesión ya inactiva."""
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=15))
            r = refresh(t["refresh"]); assert r.status_code == 200
            ft.tick(timedelta(minutes=16))
            assert get("/users/", r.data["access"], idle=0).status_code == 401

    def test_legacy_client_without_header_counts_as_activity(self, admin_user, settings):
        settings.AUTH_ACTIVITY_HEADER_REQUIRED = False
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=15))
            r = refresh(t["refresh"])
            assert get("/users/", r.data["access"]).status_code == 200
            ft.tick(timedelta(minutes=16))
            assert refresh(r.data["refresh"]).status_code == 200

    def test_header_required_mode(self, admin_user, settings):
        settings.AUTH_ACTIVITY_HEADER_REQUIRED = True
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=15))
            r = refresh(t["refresh"])
            assert get("/users/", r.data["access"]).status_code == 200  # sin header: no cuenta
            ft.tick(timedelta(minutes=16))
            assert refresh(r.data["refresh"]).status_code == 401

    @pytest.mark.parametrize("bad", ["abc", "-5", "nan"])
    def test_invalid_idle_header_is_not_activity(self, admin_user, bad):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=15))
            r = refresh(t["refresh"])
            assert get("/users/", r.data["access"], idle=bad).status_code == 200
            ft.tick(timedelta(minutes=16))
            assert refresh(r.data["refresh"]).status_code == 401


@pytest.mark.django_db
class TestLogout:
    def test_logout_revokes_access_and_refresh_immediately(self, admin_user):
        t = login(admin_user)
        c = APIClient()
        r = c.post("/logout/", {"refresh_token": t["refresh"]}, format="json",
                   HTTP_AUTHORIZATION=f"Bearer {t['access']}")
        assert r.status_code == 200
        assert get("/users/", t["access"], idle=0).status_code == 401
        assert refresh(t["refresh"]).status_code == 401

    def test_logout_only_affects_that_session(self, admin_user):
        t1, t2 = login(admin_user), login(admin_user)
        APIClient().post("/logout/", {"refresh_token": t1["refresh"]}, format="json")
        assert get("/users/", t1["access"], idle=0).status_code == 401
        assert get("/users/", t2["access"], idle=0).status_code == 200

    def test_logout_with_expired_access_uses_refresh(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            t = login(admin_user)
            ft.tick(timedelta(minutes=25))
            r = APIClient().post("/logout/", {"refresh_token": t["refresh"]}, format="json",
                                 HTTP_AUTHORIZATION=f"Bearer {t['access']}")
            assert r.status_code == 200
            assert AuthSession.objects.get(pk=claims(t["refresh"])["sid"]).revoked_at is not None

    def test_logout_all(self, admin_user):
        t1, t2 = login(admin_user), login(admin_user)
        r = APIClient().post("/logout/", {"refresh_token": t1["refresh"], "all": True}, format="json")
        assert r.status_code == 200
        for t in (t1, t2):
            assert get("/users/", t["access"], idle=0).status_code == 401
            assert refresh(t["refresh"]).status_code == 401
        admin_user.refresh_from_db()
        assert admin_user.token_version == 1
        login(admin_user)  # se puede volver a entrar

    def test_logout_without_tokens_is_401(self, db):
        assert APIClient().post("/logout/", {}, format="json").status_code == 401

    def test_logout_garbage_token_is_401(self, db):
        assert APIClient().post("/logout/", {"refresh_token": "x.y.z"}, format="json").status_code == 401


@pytest.mark.django_db
class TestTokenVersionAndAdminCreate:
    def test_token_version_bump_revokes_everything(self, admin_user):
        t = login(admin_user)
        admin_user.token_version += 1
        admin_user.save(update_fields=["token_version"])
        assert get("/users/", t["access"], idle=0).status_code == 401
        assert refresh(t["refresh"]).status_code == 401

    def test_deleted_user_tokens_rejected(self, admin_user):
        t = login(admin_user)
        admin_user.delete()  # soft delete
        assert get("/users/", t["access"], idle=0).status_code == 401
        assert refresh(t["refresh"]).status_code == 401

    def test_admin_create_does_not_return_tokens(self, super_client, user_types):
        r = super_client.post("/users/", {
            "email": "nuevo@test.com", "password": "Clave-Segura-2026", "name": "N",
            "last_name": "U", "dni": "99887766", "tipo_usuario": user_types["admin"].id,
        }, format="json")
        assert r.status_code == 201, r.data
        assert "tokens" not in r.data


@pytest.mark.django_db
def test_session_status(admin_user):
    t = login(admin_user)
    r = get("/session/", t["access"], idle=0)
    assert r.status_code == 200 and r.data["idle_timeout_seconds"] == 1800


def test_cors_allows_idle_header():
    assert "x-client-idle" in settings.CORS_ALLOW_HEADERS
