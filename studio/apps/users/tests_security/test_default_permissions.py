"""Bloque 1: permisos por defecto de DRF."""
import pytest
from django.conf import settings
from django.urls import get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

# Endpoints públicos declarados explícitamente (AllowAny).
EXPECTED_PUBLIC = {
    "UserLoginViewSet", "StudentLoginViewSet", "CheckDniView", "RegisterView",
    "VerifyEmailView", "PasswordResetView", "PasswordResetConfirmView",
    "PricesViewSet", "AvailablePlansViewSet",
    # Identifican la sesión por el token del body:
    "TokenObtainView", "SessionTokenRefreshView", "LogoutView",
}


def test_default_permission_is_authenticated():
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == (
        "rest_framework.permissions.IsAuthenticated",
    )


def _drf_views():
    seen = {}
    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns)
                continue
            cls = getattr(p.callback, "cls", None)
            if cls is not None:
                seen[cls.__name__] = cls
    walk(get_resolver().url_patterns)
    return seen


def test_only_expected_views_are_public():
    """Ninguna vista queda pública por omisión: las AllowAny son exactamente las esperadas."""
    public = set()
    for name, cls in _drf_views().items():
        perms = getattr(cls, "permission_classes", [])
        if any(p is AllowAny for p in perms):
            public.add(name)
    assert public == EXPECTED_PUBLIC


@pytest.mark.django_db
def test_api_root_requires_auth():
    r = APIClient().get("/")
    assert r.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/people/", "/payments/", "/users/", "/expenses/", "/statistics/" ])
def test_private_endpoints_reject_anonymous(url):
    r = APIClient().get(url)
    assert r.status_code in (401, 403, 404)
    if r.status_code == 404:
        assert url == "/statistics/"


@pytest.mark.django_db
def test_public_endpoints_still_reachable(user_types):
    c = APIClient()
    assert c.get("/available-plans/").status_code == 200
    assert c.post("/login/", {"identifier": "x@x.com", "password": "bad"}, format="json").status_code == 400
