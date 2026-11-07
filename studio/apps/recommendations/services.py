from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from django.db.models import Count, Q
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.rooms.models import Room
from apps.slots.models import FixedSlot, Slot, SlotTemplate
from apps.slots.services import WEEKDAY_NAMES
from apps.teachers_turn.models import TeachersTurn
from apps.waiting_list.models import WaitingList

from .models import Recommendation, RecommendationAnalysis


def occupancy_of(confirmed, availability):
    cupos = (availability or 0) + (confirmed or 0)
    if cupos <= 0:
        return 0.0
    return (confirmed or 0) / cupos


def ratio_at_least(values, threshold):
    if not values:
        return 0.0
    return sum(1 for v in values if v >= threshold) / len(values)


def ratio_at_most(values, threshold):
    if not values:
        return 0.0
    return sum(1 for v in values if v <= threshold) / len(values)


@dataclass
class Params:
    window_weeks: int
    min_classes: int
    high_occupancy_threshold: float
    high_occupancy_ratio: float
    low_occupancy_threshold: float
    low_occupancy_ratio: float


def classify(occupancies, params):
    if len(occupancies) < params.min_classes:
        return 'insufficient'
    if ratio_at_least(occupancies, params.high_occupancy_threshold) >= params.high_occupancy_ratio:
        return 'high'
    if ratio_at_most(occupancies, params.low_occupancy_threshold) >= params.low_occupancy_ratio:
        return 'low'
    return 'medium'


FranjaKey = namedtuple('FranjaKey', 'studio_id room_id activity_subtype_id weekday start_time')


def class_start(slot):
    """Inicio de la clase como datetime con zona horaria (la del proyecto)."""
    return timezone.make_aware(datetime.combine(slot.date, slot.start_time),
                               timezone.get_current_timezone())


def late_cancellations(slots):
    """Reservas dadas de baja despues del inicio de su clase, por slot.

    Esas reservas estaban confirmadas al empezar la clase: cuentan para la
    ocupacion historica aunque hoy figuren dadas de baja. No se modifica nada.
    """
    starts = {s.id: class_start(s) for s in slots}
    late = defaultdict(int)
    if not starts:
        return late
    rows = (Appointment.all_objects
            .filter(slot_id__in=list(starts), deleted__isnull=False)
            .values_list('slot_id', 'deleted'))
    for slot_id, deleted in rows:
        if deleted > starts[slot_id]:
            late[slot_id] += 1
    return late


def scan_franjas(window_start, window_end):
    """Devuelve (ocupaciones por franja, meta por franja).

    La ocupacion de cada clase usa las reservas confirmadas al inicio de la
    clase: las vigentes mas las dadas de baja despues de ese momento.
    meta = {'end_time': end_time de la ultima observacion, 'cupos': maximo de cupos observado}.
    """
    slots = list(
        Slot.objects
        .filter(date__gte=window_start, date__lt=window_end,
                date__isnull=False, start_time__isnull=False, room__isnull=False)
        .select_related('room')
        .annotate(confirmed=Count('appointments', filter=Q(appointments__deleted__isnull=True)))
    )
    late = late_cancellations(slots)
    franjas = defaultdict(list)
    meta = {}
    last_date = {}
    for s in slots:
        key = FranjaKey(s.room.studio_id, s.room_id, s.activity_subtype_id,
                        s.date.weekday(), s.start_time)
        active = s.confirmed or 0
        # cupos habilitados: cada baja devuelve su lugar a availability, asi que
        # disponibles + vigentes conserva los cupos de la clase.
        cupos = (s.availability or 0) + active
        at_start = active + late.get(s.id, 0)
        franjas[key].append(occupancy_of(at_start, max(cupos - at_start, 0)))
        m = meta.setdefault(key, {'end_time': None, 'cupos': 0})
        m['cupos'] = max(m['cupos'], cupos)
        if s.end_time is not None and (key not in last_date or s.date >= last_date[key]):
            m['end_time'] = s.end_time
            last_date[key] = s.date
    return dict(franjas), meta


def build_franjas(window_start, window_end):
    return scan_franjas(window_start, window_end)[0]


def waitlist_count(studio_id, room_id, weekday, start_time, window_start, window_end):
    # dedup por persona; weekday se filtra en Python (no portable en el ORM).
    persons = set()
    for w in WaitingList.all_objects.filter(
            slot__room_id=room_id, slot__start_time=start_time,
            slot__date__gte=window_start, slot__date__lt=window_end).select_related('slot'):
        if w.slot and w.slot.date and w.slot.date.weekday() == weekday:
            persons.add(w.person_id)
    return len(persons)


def affected_count(room_id, activity_subtype_id, weekday, start_time, window_start, window_end):
    persons = set()
    appts = Appointment.objects.filter(
        slot__room_id=room_id, slot__start_time=start_time,
        slot__date__gte=window_start, slot__date__lt=window_end,
    ).select_related('slot')
    templates = set()
    for a in appts:
        if a.slot and a.slot.date and a.slot.date.weekday() == weekday:
            persons.add(a.person_id)
            if a.slot.template_id:
                templates.add(a.slot.template_id)
    today = timezone.now().date()
    fixed = (
        FixedSlot.objects.filter(template_id__in=templates, start_date__lte=today)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        if templates else FixedSlot.objects.none()
    )
    for f in fixed:
        persons.add(f.person_id)
    return len({p for p in persons if p is not None})


def compatible_rooms(studio_id, activity_subtype_id):
    active = Room.objects.filter(studio_id=studio_id, is_active=True)
    if activity_subtype_id is not None:
        hosted_ids = Slot.objects.filter(
            room__studio_id=studio_id, activity_subtype_id=activity_subtype_id,
        ).values_list('room_id', flat=True).distinct()
        hosted = active.filter(id__in=list(hosted_ids))
        if hosted.exists():
            return list(hosted)
    return list(active)


def has_conflict(room_id, weekday, start_time, end_time):
    """True si la sala esta ocupada ese dia de la semana en [start_time, end_time):
    por una plantilla activa (grilla vigente) o por un slot futuro ya generado."""
    if SlotTemplate.objects.filter(
            room_id=room_id, is_active=True, days_of_week__day=WEEKDAY_NAMES[weekday],
            start_time__lt=end_time, end_time__gt=start_time).exists():
        return True
    today = timezone.now().date()
    overlap = (Q(start_time__lt=end_time, end_time__gt=start_time)
               | Q(end_time__isnull=True, start_time=start_time))  # sin end_time: igualdad de start
    for s in Slot.objects.filter(overlap, room_id=room_id, date__gte=today):
        if s.date and s.date.weekday() == weekday:
            return True
    return False


def _shift_end(origin_start, origin_end, new_start):
    # end del horario candidato = new_start + duracion de la franja origen.
    base = datetime(2000, 1, 1)
    dur = datetime.combine(base, origin_end) - datetime.combine(base, origin_start)
    return (datetime.combine(base, new_start) + dur).time()


def franja_teachers(key):
    """Profesoras asignadas a las clases futuras de la franja (programacion vigente)."""
    today = timezone.now().date()
    ids = set()
    for t in TeachersTurn.objects.filter(
            slot__room_id=key.room_id, slot__start_time=key.start_time,
            slot__date__gte=today).select_related('slot'):
        if t.slot.date.weekday() == key.weekday and t.teacher_id:
            ids.add(t.teacher_id)
    return ids


def teacher_conflict(teacher_ids, weekday, start_time, end_time, exclude_key=None):
    """True si alguna profesora ya tiene asignada otra clase futura que se superpone
    (en cualquier sala o sede) con ese dia y horario."""
    if not teacher_ids:
        return False
    today = timezone.now().date()
    turns = (TeachersTurn.objects
             .filter(teacher_id__in=teacher_ids, slot__date__gte=today,
                     slot__start_time__lt=end_time, slot__end_time__gt=start_time)
             .select_related('slot'))
    for t in turns:
        s = t.slot
        if s.date.weekday() != weekday:
            continue
        if exclude_key and (s.room_id, s.start_time) == (exclude_key.room_id, exclude_key.start_time):
            continue
        return True
    return False


def default_params():
    return Params(8, 8, 0.8, 0.6, 0.5, 0.6)


def _exists_decided_or_pending(type_, key):
    # cualquier estado (pending/accepted/discarded): no se regenera una franja ya tratada.
    return Recommendation.objects.filter(
        type=type_, studio_id=key.studio_id, room_id=key.room_id,
        activity_subtype_id=key.activity_subtype_id, weekday=key.weekday,
        start_time=key.start_time,
    ).exists()


def run_analysis(params, user=None):
    today = timezone.now().date()
    window_start = today - timedelta(weeks=params.window_weeks)
    window_end = today
    analysis = RecommendationAnalysis.objects.create(
        created_by=user, window_weeks=params.window_weeks,
        window_start=window_start, window_end=window_end, min_classes=params.min_classes,
        high_occupancy_threshold=params.high_occupancy_threshold,
        high_occupancy_ratio=params.high_occupancy_ratio,
        low_occupancy_threshold=params.low_occupancy_threshold,
        low_occupancy_ratio=params.low_occupancy_ratio,
    )
    franjas, meta = scan_franjas(window_start, window_end)
    rules = {
        'min_classes': params.min_classes,
        'high_occupancy_threshold': params.high_occupancy_threshold,
        'high_occupancy_ratio': params.high_occupancy_ratio,
        'low_occupancy_threshold': params.low_occupancy_threshold,
        'low_occupancy_ratio': params.low_occupancy_ratio,
    }
    insuficientes = 0
    generadas = 0
    alta_sin_recurso = []
    baja_con_espera = []
    for key, occs in franjas.items():
        kind = classify(occs, params)
        if kind == 'insufficient':
            insuficientes += 1
        if kind in ('insufficient', 'medium'):
            continue
        occupancy_avg = sum(occs) / len(occs)
        high_ratio = ratio_at_least(occs, params.high_occupancy_threshold)
        low_ratio = ratio_at_most(occs, params.low_occupancy_threshold)
        wl = waitlist_count(key.studio_id, key.room_id, key.weekday, key.start_time, window_start, window_end)
        affected = affected_count(key.room_id, key.activity_subtype_id, key.weekday, key.start_time, window_start, window_end)
        pending_conditions = ['equipamiento', 'disponibilidad_profesora']

        franja_info = {
            'studio_id': key.studio_id, 'room_id': key.room_id,
            'activity_subtype_id': key.activity_subtype_id, 'weekday': key.weekday,
            'start_time': key.start_time.strftime('%H:%M:%S'), 'observaciones': len(occs),
            'ocupacion_promedio': round(occupancy_avg, 4), 'lista_de_espera': wl,
        }
        if kind == 'high':
            alternative = _find_alternative(key, prefer_free=True, meta=meta.get(key))
            if alternative is None:
                # HU-19 c.1: sin recurso compatible y disponible no hay recomendacion
                # ejecutable; la alta demanda se informa en el resumen del analisis.
                alta_sin_recurso.append(franja_info)
                continue
            type_ = 'add'
        else:  # low
            teachers = franja_teachers(key)
            dest = _find_relocate_destination(key, franjas, meta, params, window_start, window_end,
                                              teachers=teachers)
            if dest is not None:
                type_ = 'relocate'
                alternative = dest
                if teachers:
                    # superposicion con la programacion de las profesoras ya verificada
                    pending_conditions.remove('disponibilidad_profesora')
            elif wl > 0:
                # HU-19 c.3: la lista de espera propia es evidencia para mantener la oferta.
                baja_con_espera.append(franja_info)
                continue
            else:
                type_ = 'reduce'
                alternative = _find_alternative(key, prefer_free=True, meta=meta.get(key))

        if alternative is None:
            pending_conditions.append('sin_sala_alternativa')

        if _exists_decided_or_pending(type_, key):
            continue
        Recommendation.objects.create(
            analysis=analysis, type=type_, studio_id=key.studio_id, room_id=key.room_id,
            activity_subtype_id=key.activity_subtype_id, weekday=key.weekday, start_time=key.start_time,
            period_start=window_start, period_end=window_end,
            observations_count=len(occs), occupancy_avg=occupancy_avg,
            high_ratio=high_ratio, low_ratio=low_ratio, waitlist_count=wl, affected_count=affected,
            rules_applied=rules, pending_conditions=pending_conditions, proposed_alternative=alternative,
        )
        generadas += 1
    analysis.run_summary = {
        'franjas_analizadas': len(franjas),
        'insuficientes': insuficientes,
        'generadas': generadas,
        'alta_demanda_sin_recurso': alta_sin_recurso,
        'baja_con_lista_de_espera': baja_con_espera,
    }
    return analysis


def _origin_span(key, m):
    end = (m or {}).get('end_time')
    if end is None:  # sin dato: duracion supuesta de 1h
        end = (datetime.combine(datetime(2000, 1, 1), key.start_time) + timedelta(hours=1)).time()
    return end


def _room_fits(room, cupos):
    # capacity None = desconocida: se acepta (criterio conservador).
    if room.capacity is None:
        return True
    if cupos:
        return room.capacity >= cupos
    return room.capacity > 0


def _find_alternative(key, prefer_free, meta=None):
    cupos = (meta or {}).get('cupos') or 0
    end = _origin_span(key, meta)
    for r in compatible_rooms(key.studio_id, key.activity_subtype_id):
        if has_conflict(r.id, key.weekday, key.start_time, end):
            continue
        if not _room_fits(r, cupos):
            continue
        is_new = (r.id != key.room_id)
        return {'room_id': r.id, 'room_name': r.name, 'weekday': key.weekday,
                'start_time': key.start_time.strftime('%H:%M:%S'), 'is_new_slot': is_new}
    return None


def _find_relocate_destination(key, franjas, meta, params, window_start, window_end, teachers=None):
    """Horario (weekday, hora) con demanda en OTRAS franjas de la misma actividad
    donde una sala compatible esta libre y tiene capacidad."""
    m = meta.get(key)
    origin_end = _origin_span(key, m)
    cupos = (m or {}).get('cupos') or 0
    demanded = []
    seen = set()
    for other, occs in franjas.items():
        if other.studio_id != key.studio_id or other.activity_subtype_id != key.activity_subtype_id:
            continue
        slot_time = (other.weekday, other.start_time)
        if slot_time == (key.weekday, key.start_time) or slot_time in seen:
            continue
        wl = waitlist_count(other.studio_id, other.room_id, other.weekday,
                            other.start_time, window_start, window_end)
        if wl > 0 or classify(occs, params) == 'high':
            seen.add(slot_time)
            demanded.append(slot_time)
    rooms = compatible_rooms(key.studio_id, key.activity_subtype_id)
    for wd, start in sorted(demanded):
        end = _shift_end(key.start_time, origin_end, start)
        for r in rooms:
            if has_conflict(r.id, wd, start, end) or not _room_fits(r, cupos):
                continue
            if teacher_conflict(teachers, wd, start, end, exclude_key=key):
                continue
            return {'room_id': r.id, 'room_name': r.name, 'weekday': wd,
                    'start_time': start.strftime('%H:%M:%S'), 'is_new_slot': True}
    return None
