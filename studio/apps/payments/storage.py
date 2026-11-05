"""Almacenamiento de comprobantes de pago.

- Modo privado (PRIVATE_MEDIA_ROOT definido): los PDF nuevos se guardan fuera
  de MEDIA_ROOT, en un directorio que nginx no sirve. Solo se descargan por la
  API (/payments/{id}/download_pdf/), que aplica los permisos del ViewSet.
- Modo legado (PRIVATE_MEDIA_ROOT vacío): se mantiene MEDIA_ROOT/payments/ como
  hasta ahora (servido públicamente por nginx). Es el valor por defecto para no
  cambiar la infraestructura sin autorización: activar el modo privado requiere
  un volumen persistente para PRIVATE_MEDIA_ROOT en el despliegue.

Los archivos existentes NO se mueven: la descarga los busca primero en el
almacenamiento actual y, si no están, en la ubicación legada (solo lectura).
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage


class PrivateReceiptStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None,
                         file_permissions_mode=0o600, directory_permissions_mode=0o700)

    def url(self, name):  # nunca hay URL pública
        raise ValueError("Los comprobantes privados solo se descargan por la API.")


def private_mode():
    return bool(getattr(settings, "PRIVATE_MEDIA_ROOT", None))


def receipt_storage():
    return PrivateReceiptStorage() if private_mode() else default_storage


def resolve_receipt_path(field_file):
    """Ruta absoluta del comprobante (almacenamiento actual o ubicación legada)."""
    name = field_file.name
    if not name:
        return None
    candidates = []
    try:
        candidates.append(field_file.storage.path(name))
    except Exception:
        pass
    legacy = os.path.join(settings.MEDIA_ROOT, name)
    if legacy not in candidates:
        candidates.append(legacy)
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    private_root = os.path.realpath(getattr(settings, "PRIVATE_MEDIA_ROOT", "") or media_root)
    for path in candidates:
        real = os.path.realpath(path)
        # Defensa: nunca salir de los directorios permitidos.
        if not (real.startswith(media_root + os.sep) or real.startswith(private_root + os.sep)):
            continue
        if os.path.isfile(real):
            return real
    return None
