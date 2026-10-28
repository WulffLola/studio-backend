import os

from django.db import migrations

from apps.payments.money_migration_utils import parse_amount_to_decimal_str


def normalize_amounts(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    for p in Payment.objects.exclude(amount__isnull=True):
        norm = parse_amount_to_decimal_str(p.amount)
        if norm != p.amount:
            p.amount = norm
            p.save(update_fields=['amount'])


def assign_null_studio(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Studio = apps.get_model('studios', 'Studio')
    qs = Payment.objects.filter(studio__isnull=True)
    if not qs.exists():
        return
    raw = os.getenv('KAN290_FALLBACK_STUDIO_ID')
    if not raw or not raw.isdigit() or not Studio.objects.filter(pk=int(raw)).exists():
        raise RuntimeError(
            " hay Payment con studio NULL. Seteá KAN290_FALLBACK_STUDIO_ID "
            "a un id de Studio válido antes de migrar.")
    qs.update(studio_id=int(raw))


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0009_paymentitem_discount_source'),
        ('studios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(normalize_amounts, migrations.RunPython.noop),
        migrations.RunPython(assign_null_studio, migrations.RunPython.noop),
    ]
