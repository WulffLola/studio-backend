"""Bloque 4: validadores, contraseña actual, reset de un solo uso, revocación."""
from datetime import timedelta

import pytest
from django.core import signing
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.users.models import CustomUser
from apps.users.views import make_password_reset_token

PWD = "test123"
STRONG = "Reformer-Azul-2026"


def login(user, pwd=PWD):
    r = APIClient().post("/login/", {"identifier": user.email, "password": pwd}, format="json")
    assert r.status_code == 200, r.data
    return r.data["tokens"]


def authed(tokens):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}", HTTP_X_CLIENT_IDLE="0")
    return c


WEAK = ["123", "12345678", "password", "pilates"]


@pytest.mark.django_db
class TestValidatorsEverywhere:
    @pytest.mark.parametrize("weak", WEAK)
    def test_register_new(self, user_types, weak):
        r = APIClient().post("/register/", {"dni": "40111222", "email": "n@t.com", "password": weak,
                                            "name": "Nora", "last_name": "Paz"}, format="json")
        assert r.status_code == 400 and "password" in r.data
        assert not CustomUser.all_objects.filter(dni="40111222").exists()

    def test_register_similar_to_email_rejected(self, user_types):
        r = APIClient().post("/register/", {"dni": "40111223", "email": "noralopez@t.com",
                                            "password": "noralopez", "name": "Nora", "last_name": "Lopez"}, format="json")
        assert r.status_code == 400 and "password" in r.data

    def test_register_existing_person(self, user_types):
        from apps.people.models import Person
        Person.objects.create(name="Ana", last_name="Lopez", dni="55556666", email="ana@test.com")
        r = APIClient().post("/register/", {"dni": "55556666", "email": "ana@test.com", "password": "12345678"}, format="json")
        assert r.status_code == 400 and "password" in r.data
        r = APIClient().post("/register/", {"dni": "55556666", "email": "ana@test.com", "password": STRONG}, format="json")
        assert r.status_code == 201

    @pytest.mark.parametrize("weak", WEAK)
    def test_admin_create(self, super_client, user_types, weak):
        r = super_client.post("/users/", {"email": "nn@t.com", "password": weak, "name": "N", "last_name": "U",
                                          "dni": "99887766", "tipo_usuario": user_types["admin"].id}, format="json")
        assert r.status_code == 400 and "password" in r.data

    def test_admin_update_other_user(self, super_client, admin_user):
        r = super_client.patch(f"/users/{admin_user.pk}/", {"password": "12345678"}, format="json")
        assert r.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.check_password(PWD)

    def test_reset_confirm(self, admin_user):
        tok = make_password_reset_token(admin_user)
        r = APIClient().post("/password-reset/confirm/", {"token": tok, "password": "12345678"}, format="json")
        assert r.status_code == 400 and "password" in r.data
        # el token sigue sirviendo porque no se cambió la contraseña
        r = APIClient().post("/password-reset/confirm/", {"token": tok, "password": STRONG}, format="json")
        assert r.status_code == 200

    def test_hashing_is_django_pbkdf2(self, admin_user):
        assert admin_user.password.startswith("pbkdf2_sha256$")


@pytest.mark.django_db
class TestCurrentPassword:
    def test_self_change_requires_current_password(self, admin_user):
        t = login(admin_user)
        c = authed(t)
        assert c.patch(f"/users/{admin_user.pk}/", {"password": STRONG}, format="json").status_code == 400
        r = c.patch(f"/users/{admin_user.pk}/", {"password": STRONG, "current_password": "mala"}, format="json")
        assert r.status_code == 400 and "current_password" in r.data
        r = c.patch(f"/users/{admin_user.pk}/", {"password": STRONG, "current_password": PWD}, format="json")
        assert r.status_code == 200, r.data
        admin_user.refresh_from_db()
        assert admin_user.check_password(STRONG)

    def test_self_change_keeps_current_session_revokes_others(self, admin_user):
        t1, t2 = login(admin_user), login(admin_user)
        r = authed(t1).patch(f"/users/{admin_user.pk}/", {"password": STRONG, "current_password": PWD}, format="json")
        assert r.status_code == 200
        assert authed(t1).get("/session/").status_code == 200
        assert authed(t2).get("/session/").status_code == 401
        assert APIClient().post("/token/refresh/", {"refresh": t2["refresh"]}, format="json").status_code == 401

    def test_student_self_change(self, student_user):
        t = login(student_user)
        c = authed(t)
        assert c.patch(f"/users/{student_user.pk}/", {"password": STRONG}, format="json").status_code == 400
        r = c.patch(f"/users/{student_user.pk}/", {"password": STRONG, "current_password": PWD}, format="json")
        assert r.status_code == 200, r.data

    def test_wrong_current_password_counts_for_lockout(self, admin_user):
        t = login(admin_user)
        c = authed(t)
        for _ in range(5):
            c.patch(f"/users/{admin_user.pk}/", {"password": STRONG, "current_password": "mala"}, format="json")
        r = c.patch(f"/users/{admin_user.pk}/", {"password": STRONG, "current_password": PWD}, format="json")
        assert r.status_code == 429
        assert APIClient().post("/login/", {"identifier": admin_user.email, "password": PWD}, format="json").status_code == 429

    def test_admin_changes_other_without_current_and_revokes_target(self, admin_user, user_types):
        consultor = CustomUser.objects.create_user(email="c@t.com", password=PWD, name="C", last_name="C",
                                                   dni="11223344", tipo_usuario=user_types["consultor"])
        tc = login(consultor)
        ta = login(admin_user)
        r = authed(ta).patch(f"/users/{consultor.pk}/", {"password": STRONG}, format="json")
        assert r.status_code == 200, r.data
        assert authed(tc).get("/session/").status_code == 401
        assert authed(ta).get("/session/").status_code == 200

    def test_profile_edit_without_password_unchanged(self, admin_user):
        t = login(admin_user)
        r = authed(t).patch(f"/users/{admin_user.pk}/", {"name": "Otro"}, format="json")
        assert r.status_code == 200


@pytest.mark.django_db
class TestResetTokens:
    def test_login_after_request_invalidates_link(self, admin_user):
        tok = make_password_reset_token(admin_user)
        login(admin_user)
        r = APIClient().post("/password-reset/confirm/", {"token": tok, "password": STRONG}, format="json")
        assert r.status_code == 400  # comportamiento estándar de Django (depende de last_login)

    def test_single_use(self, admin_user):
        tok = make_password_reset_token(admin_user)
        assert APIClient().post("/password-reset/confirm/", {"token": tok, "password": STRONG}, format="json").status_code == 200
        r = APIClient().post("/password-reset/confirm/", {"token": tok, "password": "Otra-Clave-9911"}, format="json")
        assert r.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.check_password(STRONG)

    def test_expires_after_one_hour(self, admin_user):
        with freeze_time("2026-11-05 10:00:00") as ft:
            tok = make_password_reset_token(admin_user)
            ft.tick(timedelta(minutes=61))
            r = APIClient().post("/password-reset/confirm/", {"token": tok, "password": STRONG}, format="json")
            assert r.status_code == 400 and "expiró" in r.data["detail"]

    def test_old_format_token_rejected(self, admin_user):
        tok = signing.dumps(admin_user.pk, salt="password-reset")
        r = APIClient().post("/password-reset/confirm/", {"token": tok, "password": STRONG}, format="json")
        assert r.status_code == 400

    def test_tampered_token_rejected(self, admin_user, user_types):
        other = CustomUser.objects.create_user(email="o@t.com", password=PWD, name="O", last_name="O", dni="10101010")
        tok = make_password_reset_token(other)
        payload = signing.loads(tok, salt="password-reset")
        forged = signing.dumps({"u": admin_user.pk, "t": payload["t"]}, salt="password-reset")
        assert APIClient().post("/password-reset/confirm/", {"token": forged, "password": STRONG}, format="json").status_code == 400

    def test_reset_revokes_all_sessions_and_unlocks(self, admin_user):
        t = login(admin_user)
        for _ in range(5):
            APIClient().post("/login/", {"identifier": admin_user.email, "password": "mala"}, format="json")
        admin_user.refresh_from_db()  # el token depende de last_login (actualizado por el login)
        tok = make_password_reset_token(admin_user)
        assert APIClient().post("/password-reset/confirm/", {"token": tok, "password": STRONG}, format="json").status_code == 200
        assert authed(t).get("/session/").status_code == 401
        assert APIClient().post("/token/refresh/", {"refresh": t["refresh"]}, format="json").status_code == 401
        login(admin_user, STRONG)  # desbloqueada y con la nueva clave

    def test_request_endpoint_sends_new_format(self, admin_user, monkeypatch):
        sent = {}
        monkeypatch.setattr("apps.users.views.send_password_reset_email",
                            lambda email, name, token: sent.update(token=token))
        r = APIClient().post("/password-reset/", {"email": admin_user.email}, format="json")
        assert r.status_code == 200
        assert APIClient().post("/password-reset/confirm/", {"token": sent["token"], "password": STRONG}, format="json").status_code == 200

    def test_request_same_response_for_unknown_email(self, db, monkeypatch):
        monkeypatch.setattr("apps.users.views.send_password_reset_email", lambda *a: None)
        r = APIClient().post("/password-reset/", {"email": "nadie@t.com"}, format="json")
        assert r.status_code == 200
