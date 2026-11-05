"""Utilidades de red para seguridad (IP del cliente)."""
import ipaddress

from django.conf import settings


def client_ip(request):
    """IP del cliente.

    Detrás de N proxies de confianza (``AUTH_PROXY_COUNT``, por defecto 1: el
    nginx del repo, que agrega la IP real con ``$proxy_add_x_forwarded_for``)
    se toma la N-ésima IP desde la derecha de X-Forwarded-For; las entradas más
    a la izquierda las controla el cliente y no se usan. Sin el header se usa
    REMOTE_ADDR.
    """
    remote = request.META.get("REMOTE_ADDR") or None
    count = int(getattr(settings, "AUTH_PROXY_COUNT", 0) or 0)
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if count > 0 and xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= count:
            candidate = parts[-count]
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    return remote
