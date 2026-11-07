"""Copia los comprobantes existentes de MEDIA_ROOT a PRIVATE_MEDIA_ROOT.

Seguro por diseño:
- Por defecto es simulación (--ejecutar para copiar).
- COPIA, no mueve ni borra: los originales quedan intactos.
- Verifica cada copia con SHA-256; si una no coincide, la informa y no la da por buena.
- No modifica la base de datos (se conserva el mismo nombre relativo).
Borrar los originales públicos es un paso manual posterior, una vez
verificado el resultado y con autorización.
"""
import hashlib
import os
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments.models import Payment


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Copia (sin mover) los comprobantes públicos al almacenamiento privado, con verificación."

    def add_arguments(self, parser):
        parser.add_argument("--ejecutar", action="store_true", help="copiar de verdad (por defecto: simulación)")

    def handle(self, ejecutar=False, **opts):
        private_root = getattr(settings, "PRIVATE_MEDIA_ROOT", "")
        if not private_root:
            raise CommandError("PRIVATE_MEDIA_ROOT no está configurado.")
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        private_root = os.path.realpath(private_root)
        if private_root == media_root or private_root.startswith(media_root + os.sep):
            raise CommandError("PRIVATE_MEDIA_ROOT no puede estar dentro de MEDIA_ROOT.")

        stats = {"copiar": 0, "ya_copiado": 0, "faltante": 0, "error": 0}
        for name in Payment.all_objects.exclude(pdf_file="").exclude(pdf_file__isnull=True).values_list("pdf_file", flat=True):
            src = os.path.realpath(os.path.join(media_root, name))
            dst = os.path.realpath(os.path.join(private_root, name))
            if not src.startswith(media_root + os.sep) or not dst.startswith(private_root + os.sep):
                stats["error"] += 1
                self.stderr.write(f"Ruta fuera de los directorios permitidos: {name}")
                continue
            if not os.path.isfile(src):
                if os.path.isfile(dst):
                    stats["ya_copiado"] += 1
                else:
                    stats["faltante"] += 1
                    self.stderr.write(f"No existe el original: {name}")
                continue
            if os.path.isfile(dst) and sha256(dst) == sha256(src):
                stats["ya_copiado"] += 1
                continue
            stats["copiar"] += 1
            if ejecutar:
                os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
                shutil.copy2(src, dst)
                os.chmod(dst, 0o600)
                if sha256(dst) != sha256(src):
                    stats["error"] += 1
                    self.stderr.write(f"Verificación fallida: {name}")
        modo = "EJECUCIÓN" if ejecutar else "SIMULACIÓN"
        self.stdout.write(f"[{modo}] " + ", ".join(f"{k}={v}" for k, v in stats.items()))
