from decimal import Decimal, InvalidOperation
from django.db import models
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from apps.plans_type.models import ComboPlanDiscount


def normalize_and_validate_items(items_data):
    """
    Normaliza y valida los items de un pago multi-plan.

    Devuelve (norm_items, None) si es válido, o (None, mensaje_error) si hay un
    error de request; la vista traduce el mensaje a un 400 {"detail": mensaje}.
    norm_items = lista de {'plans_subtype_id', 'base_amount'}.
    """
    from apps.plans_subtype.models import PlansSubtype
    try:
        norm_items = [
            {'plans_subtype_id': it['plans_subtype_id'], 'base_amount': it['base_amount']}
            for it in items_data
        ]
    except (KeyError, TypeError):
        return None, "Cada item requiere 'plans_subtype_id' y 'base_amount'."

    for it in norm_items:
        try:
            amount = Decimal(str(it['base_amount']))
        except (InvalidOperation, ValueError, TypeError):
            return None, f"El monto '{it['base_amount']}' del item no es válido."
        if amount < 0:
            return None, f"El monto '{it['base_amount']}' del item no es válido."

    subtype_ids = []
    for it in norm_items:
        try:
            subtype_ids.append(int(it['plans_subtype_id']))
        except (ValueError, TypeError):
            return None, f"El plan '{it['plans_subtype_id']}' no es válido."
    existing_ids = set(
        PlansSubtype.objects.filter(pk__in=subtype_ids).values_list('id', flat=True)
    )
    missing = [sid for sid in subtype_ids if sid not in existing_ids]
    if missing:
        return None, f"Los siguientes planes no existen: {missing}."

    return norm_items, None


def check_plans_availability(plans_subtype_ids):
    """
    Verifica si cada PlansSubtype tiene al menos un Slot disponible
    (availability > 0, no eliminado, fecha presente o futura).

    Retorna lista de dicts para los subtypes SIN clases disponibles:
        [{"plans_subtype_id": int, "plans_subtype_name": str}, ...]
    """
    from apps.slots.models import Slot
    from apps.plans_subtype.models import PlansSubtype

    today = timezone.now().date()
    unavailable = []

    for ps_id in plans_subtype_ids:
        try:
            ps = PlansSubtype.objects.select_related('activity_subtype').get(pk=ps_id)
        except (PlansSubtype.DoesNotExist, ValueError, TypeError):
            unavailable.append({'plans_subtype_id': ps_id, 'plans_subtype_name': f'ID {ps_id}'})
            continue

        if not ps.activity_subtype_id:
            continue

        has_slot = Slot.objects.filter(
            activity_subtype=ps.activity_subtype,
            availability__gt=0,
            deleted__isnull=True,
        ).filter(
            models.Q(date__gte=today) | models.Q(date__isnull=True)
        ).exists()

        if not has_slot:
            unavailable.append({'plans_subtype_id': ps_id, 'plans_subtype_name': ps.name})

    return unavailable


def find_applicable_combos(subtype_ids):
    """
    Busca combos que se activan dado un conjunto de plans_subtype_ids.
    Un combo aplica cuando TODOS sus planes están presentes en subtype_ids.

    Retorna lista de dicts:
        [{
            'combo_id': int,
            'combo_name': str,
            'discount_pct': Decimal,
            'matching_subtype_ids': [int, ...],
        }, ...]
    """
    combos = (
        ComboPlanDiscount.objects
        .prefetch_related('plans')
        .filter(deleted__isnull=True)
    )

    subtype_ids_set = set(subtype_ids)
    applicable = []

    for combo in combos:
        combo_plan_ids = set(combo.plans.values_list('id', flat=True))
        if combo_plan_ids and combo_plan_ids.issubset(subtype_ids_set):
            applicable.append({
                'combo_id': combo.id,
                'combo_name': combo.name,
                'discount_pct': combo.discount_pct,
                'matching_subtype_ids': sorted(combo_plan_ids & subtype_ids_set),
            })

    return applicable


def find_applicable_plan_discounts(subtype_ids):
    """Máximo PlanDiscount vivo por plans_subtype. Retorna {subtype_id: Decimal(pct)}."""
    from apps.plans_type.models import PlanDiscount
    result = {}
    for pd in PlanDiscount.objects.filter(
        plans_subtype_id__in=subtype_ids, deleted__isnull=True,
    ):
        if pd.discount_pct > result.get(pd.plans_subtype_id, Decimal('0')):
            result[pd.plans_subtype_id] = pd.discount_pct
    return result


def apply_combo_discounts(items):
    """
    Calcula el descuento por ítem combinando combos y descuentos por plan.
    Regla: se aplica el MAYOR entre el combo y el PlanDiscount del plan.

    returns: (enriched_items, applicable_combos)
        enriched_items: cada item con 'discount_pct', 'discount_source' y 'final_amount'.
    """
    subtype_ids = [item['plans_subtype_id'] for item in items]
    applicable_combos = find_applicable_combos(subtype_ids)

    combo_by_subtype = {}
    for combo in applicable_combos:
        for sid in combo['matching_subtype_ids']:
            if combo['discount_pct'] > combo_by_subtype.get(sid, Decimal('0')):
                combo_by_subtype[sid] = combo['discount_pct']

    plan_by_subtype = find_applicable_plan_discounts(subtype_ids)

    result = []
    for item in items:
        base = Decimal(str(item['base_amount']))
        sid = item['plans_subtype_id']
        combo_pct = combo_by_subtype.get(sid, Decimal('0'))
        plan_pct = plan_by_subtype.get(sid, Decimal('0'))
        pct = max(combo_pct, plan_pct)
        if plan_pct >= combo_pct and plan_pct > 0:
            # En empate gana 'plan' (más específico) para no atribuir mal el
            # descuento en auditoría de PaymentItem.discount_source.
            source = 'plan'
        elif combo_pct > 0:
            source = 'combo'
        else:
            source = 'none'
        result.append({
            **item,
            'discount_pct': pct,
            'discount_source': source,
            'final_amount': base * (1 - pct / 100),
        })

    return result, applicable_combos


def build_payment_items(items):
    """
    A partir de una lista de items {'plans_subtype_id', 'base_amount'} aplica los
    descuentos por combo y calcula el total.

    Retorna (enriched_items, applied_combos, total):
        - enriched_items: cada item con 'discount_pct' y 'final_amount'
        - applied_combos: combos que se activaron
        - total: Decimal cuantizado a 2 decimales (suma de final_amount), igual
          a lo que persiste cada PaymentItem.final_amount.
    """
    enriched, applied_combos = apply_combo_discounts(items)
    cents = Decimal('0.01')
    total = sum(
        (item['final_amount'].quantize(cents) for item in enriched),
        Decimal('0'),
    )
    return enriched, applied_combos, total


def _extend_one_month(current_exp_date, today):
    """
    Nueva exp_date al renovar un plan activo.

    Si la exp_date actual es futura se extiende desde ahí (renovación
    anticipada); si está vencida o es None se calcula desde la fecha de pago.
    """
    if current_exp_date and current_exp_date >= today:
        return current_exp_date + relativedelta(months=1)
    return today + relativedelta(months=1)


def register_active_plans(person, enriched_items, payment_date):
    """
    Crea o renueva el PersonActivePlan del alumno por cada item del pago.

    - Si ya existe un plan activo (no eliminado) de ese plans_subtype, lo renueva:
      extiende exp_date un mes y recarga las sesiones del subplan.
    - Si no existe, lo crea con exp_date = fecha_pago + 1 mes y las sesiones que
      define el plans_subtype (0 si no define).

    Retorna la lista de PersonActivePlan creados/renovados.
    """
    from apps.people.models import PersonActivePlan
    from apps.plans_subtype.models import PlansSubtype

    today = payment_date.date() if hasattr(payment_date, 'date') else payment_date
    affected = []

    for item in enriched_items:
        ps = PlansSubtype.objects.get(pk=item['plans_subtype_id'])
        sessions = ps.sessions or 0

        existing = (
            PersonActivePlan.objects
            .filter(person=person, plans_subtype=ps)
            .order_by('-exp_date')
            .first()
        )

        if existing:
            existing.exp_date = _extend_one_month(existing.exp_date, today)
            existing.sessions_total += sessions
            existing.sessions_remaining += sessions
            existing.save(update_fields=['exp_date', 'sessions_total', 'sessions_remaining'])
            affected.append(existing)
        else:
            affected.append(PersonActivePlan.objects.create(
                person=person,
                plans_subtype=ps,
                exp_date=today + relativedelta(months=1),
                sessions_total=sessions,
                sessions_remaining=sessions,
            ))

    return affected
