"""Bloque 5: comprobantes privados y descarga autorizada."""
import os

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.payments.models import Payment
from apps.payments.storage import PrivateReceiptStorage, resolve_receipt_path

PDF = b"%PDF-1.4 comprobante de prueba"


@pytest.fixture
def dirs(tmp_path, settings):
    media, private = tmp_path / "media", tmp_path / "private"
    media.mkdir(); private.mkdir()
    settings.MEDIA_ROOT = str(media)
    settings.PRIVATE_MEDIA_ROOT = str(private)
    return media, private


@pytest.fixture
def private_field(dirs):
    field = Payment._meta.get_field("pdf_file")
    old = field.storage
    field.storage = PrivateReceiptStorage()
    yield
    field.storage = old


@pytest.fixture
def payment(person, studio):
    return Payment.objects.create(person=person, studio=studio, date=timezone.now(), amount=100)


@pytest.mark.django_db
class TestPrivateStorage:
    def test_new_receipt_saved_outside_media_root(self, private_field, dirs, payment):
        media, private = dirs
        payment.pdf_file.save("abc.pdf", ContentFile(PDF), save=True)
        assert (private / "payments" / "abc.pdf").read_bytes() == PDF
        assert not (media / "payments" / "abc.pdf").exists()
        with pytest.raises(ValueError):
            payment.pdf_file.url

    def test_serializer_exposes_api_url_not_media(self, private_field, payment, admin_client):
        payment.pdf_file.save("abc.pdf", ContentFile(PDF), save=True)
        r = admin_client.get(f"/payments/{payment.pk}/")
        assert r.status_code == 200
        assert r.data["pdf_file"].endswith(f"/payments/{payment.pk}/download_pdf/")
        assert "/media/" not in r.data["pdf_file"]

    def test_client_cannot_set_pdf_file(self, payment, admin_client):
        from apps.payments.serializer import PaymentSerializer
        s = PaymentSerializer(payment, data={"pdf_file": "../../etc/passwd"}, partial=True)
        assert s.is_valid(), s.errors
        assert "pdf_file" not in s.validated_data


@pytest.mark.django_db
class TestDownloadAuthorization:
    @pytest.mark.parametrize("url", ["/payments/{}/download_pdf/", "/payments/download/{}/"])
    def test_admin_downloads(self, private_field, payment, admin_client, url):
        payment.pdf_file.save("abc.pdf", ContentFile(PDF), save=True)
        r = admin_client.get(url.format(payment.pk))
        assert r.status_code == 200
        assert b"".join(r.streaming_content) == PDF
        assert r["Cache-Control"] == "private, no-store"
        assert r["Content-Disposition"].startswith('attachment; filename="CP_')

    def test_anonymous_401(self, private_field, payment):
        payment.pdf_file.save("abc.pdf", ContentFile(PDF), save=True)
        assert APIClient().get(f"/payments/{payment.pk}/download_pdf/").status_code == 401

    def test_student_forbidden(self, private_field, payment, student_client):
        payment.pdf_file.save("abc.pdf", ContentFile(PDF), save=True)
        assert student_client.get(f"/payments/{payment.pk}/download_pdf/").status_code == 403

    def test_legacy_public_file_still_downloadable_without_moving(self, private_field, dirs, payment, admin_client):
        media, private = dirs
        (media / "payments").mkdir()
        legacy = media / "payments" / "CP_2026-01-01_123.pdf"
        legacy.write_bytes(PDF)
        Payment.objects.filter(pk=payment.pk).update(pdf_file="payments/CP_2026-01-01_123.pdf")
        payment.refresh_from_db()
        r = admin_client.get(f"/payments/{payment.pk}/download_pdf/")
        assert r.status_code == 200 and b"".join(r.streaming_content) == PDF
        assert legacy.exists()  # no se movió ni borró

    def test_path_traversal_name_not_served(self, private_field, dirs, payment, admin_client, tmp_path):
        secret = tmp_path / "secret.pdf"
        secret.write_bytes(b"secreto")
        Payment.objects.filter(pk=payment.pk).update(pdf_file="../secret.pdf")
        payment.refresh_from_db()
        assert resolve_receipt_path(payment.pdf_file) is None
        assert admin_client.get(f"/payments/{payment.pk}/download_pdf/").status_code == 404


@pytest.mark.django_db
class TestMigrationCommand:
    def _legacy(self, media, payment, name="CP_x.pdf"):
        (media / "payments").mkdir(exist_ok=True)
        (media / "payments" / name).write_bytes(PDF)
        Payment.objects.filter(pk=payment.pk).update(pdf_file=f"payments/{name}")

    def test_dry_run_copies_nothing(self, dirs, payment, capsys):
        media, private = dirs
        self._legacy(media, payment)
        call_command("migrar_comprobantes_privados")
        assert not (private / "payments" / "CP_x.pdf").exists()
        assert "SIMULACIÓN" in capsys.readouterr().out

    def test_execute_copies_verifies_and_keeps_original(self, dirs, payment, capsys):
        media, private = dirs
        self._legacy(media, payment)
        call_command("migrar_comprobantes_privados", ejecutar=True)
        assert (private / "payments" / "CP_x.pdf").read_bytes() == PDF
        assert (media / "payments" / "CP_x.pdf").exists()
        out = capsys.readouterr().out
        assert "copiar=1" in out and "error=0" in out
        call_command("migrar_comprobantes_privados", ejecutar=True)  # idempotente
        assert "ya_copiado=1" in capsys.readouterr().out

    def test_refuses_private_inside_media(self, dirs, settings):
        from django.core.management.base import CommandError
        settings.PRIVATE_MEDIA_ROOT = os.path.join(settings.MEDIA_ROOT, "priv")
        with pytest.raises(CommandError):
            call_command("migrar_comprobantes_privados")


@pytest.mark.django_db
class TestRealPdfGeneration:
    def test_generate_and_send_use_private_storage(self, private_field, dirs, payment, person, monkeypatch):
        from decimal import Decimal
        from apps.payments.views import PaymentViewSet
        media, private = dirs
        path = PaymentViewSet().generate_pdf_multi(
            payment, person, [], [{"plans_subtype_id": 999, "final_amount": Decimal("100")}])
        payment.refresh_from_db()
        assert path.startswith(str(private)) and os.path.isfile(path)
        assert open(path, "rb").read(4) == b"%PDF"
        assert not any(media.rglob("*.pdf"))  # nada en el directorio público
        assert "CP_" not in payment.pdf_file.name  # nombre no predecible
        # WhatsApp recibe el archivo con el nombre amigable
        sent = {}

        class R:
            def raise_for_status(self): pass

        def fake_post(url, data=None, files=None):
            sent["name"] = files["pdf"][0]
            sent["bytes"] = files["pdf"][1].read(4)
            return R()
        monkeypatch.setenv("API_WPP_SEND_PDF", "http://wpp.local/send")
        monkeypatch.setattr("apps.payments.views.requests.post", fake_post)
        person.phone = "1155550000"
        PaymentViewSet().send_pdf(path, person, "hola")
        assert sent["name"].startswith("CP_") and sent["bytes"] == b"%PDF"

    def test_legacy_mode_unchanged_location(self, dirs, payment, person, settings):
        """Sin PRIVATE_MEDIA_ROOT (valor por defecto) sigue en MEDIA_ROOT/payments."""
        from decimal import Decimal
        from apps.payments.views import PaymentViewSet
        settings.PRIVATE_MEDIA_ROOT = ""
        media, _ = dirs
        path = PaymentViewSet().generate_pdf_multi(
            payment, person, [], [{"plans_subtype_id": 1, "final_amount": Decimal("50")}])
        assert path.startswith(str(media / "payments"))
