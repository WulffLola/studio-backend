import os

from django.db import migrations

from apps.payments.money_migration_utils import parse_amount_to_decimal_str


def normalize_amounts(apps, schema_editor):
    Expense = apps.get_model('expenses', 'Expense')
    for e in Expense.objects.exclude(amount__isnull=True):
        norm = parse_amount_to_decimal_str(e.amount)
        if norm != e.amount:
            e.amount = norm
            e.save(update_fields=['amount'])


def assign_null_studio(apps, schema_editor):
    Expense = apps.get_model('expenses', 'Expense')
    Studio = apps.get_model('studios', 'Studio')
    qs = Expense.objects.filter(studio__isnull=True)
    if not qs.exists():
        return
    raw = os.getenv('KAN290_FALLBACK_STUDIO_ID')
    if not raw or not raw.isdigit() or not Studio.objects.filter(pk=int(raw)).exists():
        raise RuntimeError(
            " hay Expense con studio NULL. Seteá KAN290_FALLBACK_STUDIO_ID "
            "a un id de Studio válido antes de migrar.")
    qs.update(studio_id=int(raw))


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0002_expense_studio'),
        ('studios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(normalize_amounts, migrations.RunPython.noop),
        migrations.RunPython(assign_null_studio, migrations.RunPython.noop),
    ]
