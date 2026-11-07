"""Casos de validación del mecanismo de análisis y recomendaciones.

Cada caso replica un criterio del TFG (apartado «Validación del mecanismo» y
HU-17 a HU-19). Los resultados esperados salen de las reglas definidas; no se
ajustaron para que coincidan con la implementación. Los casos en los que el
prototipo se aparta de la regla se marcan como xfail estricto, para que la
diferencia quede visible y no se oculte.
"""
from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.recommendations.serializer import AnalyzeParamsSerializer
from apps.recommendations.services import (
    FranjaKey, Params, build_franjas, classify, default_params, occupancy_of, run_analysis,
)

P = default_params()  # 8 semanas, mínimo 8, 80 % / 60 %, 50 % / 60 %


def franja(reservas, cupos, n=8):
    """n observaciones idénticas: `reservas` confirmadas sobre `cupos` habilitados."""
    occ = occupancy_of(reservas, cupos - reservas)
    return [occ] * n


# --- V01-V02: límites de ocupación con 7 y 4 cupos -------------------------
@pytest.mark.parametrize('reservas,esperado', [
    (7, 'high'), (6, 'high'), (5, 'medium'), (4, 'medium'),
    (3, 'low'), (2, 'low'), (1, 'low'), (0, 'low'),
])
def test_v01_limites_siete_cupos(reservas, esperado):
    assert classify(franja(reservas, 7), P) == esperado


@pytest.mark.parametrize('reservas,esperado', [
    (4, 'high'), (3, 'medium'), (2, 'low'), (1, 'low'), (0, 'low'),
])
def test_v02_limites_cuatro_cupos(reservas, esperado):
    assert classify(franja(reservas, 4), P) == esperado


# --- V03-V05: recurrencia ----------------------------------------------------
def test_v03_recurrencia_exacta_60_alta():
    occs = franja(6, 7, n=6) + franja(4, 7, n=4)   # 6 de 10 = 60 %
    assert classify(occs, P) == 'high'


def test_v04_recurrencia_50_no_alcanza():
    occs = franja(6, 7, n=5) + franja(4, 7, n=5)   # 5 de 10 = 50 %
    assert classify(occs, P) == 'medium'


def test_v05_recurrencia_exacta_60_baja():
    occs = franja(3, 7, n=6) + franja(5, 7, n=4)   # 6 de 10 = 60 %
    assert classify(occs, P) == 'low'


# --- V06-V07: mínimo de observaciones ---------------------------------------
@pytest.mark.parametrize('reservas', [7, 0])
def test_v06_siete_observaciones_insuficiente(reservas):
    assert classify(franja(reservas, 7, n=7), P) == 'insufficient'


@pytest.mark.parametrize('reservas,esperado', [(7, 'high'), (0, 'low')])
def test_v07_ocho_observaciones_clasifica(reservas, esperado):
    assert classify(franja(reservas, 7, n=8), P) == esperado


# --- V08: ventana configurable entre 8 y 12 semanas ---------------------------
@pytest.mark.parametrize('semanas,valido', [(7, False), (8, True), (12, True), (13, False)])
def test_v08_ventana_8_a_12(semanas, valido):
    assert AnalyzeParamsSerializer(data={'window_weeks': semanas}).is_valid() is valido


# --- helpers con base de datos ----------------------------------------------
def _lunes_pasados(n):
    d = timezone.now().date() - timedelta(days=1)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return [d - timedelta(weeks=i) for i in range(n)]


def _clase(room, d, cupos, reservas, person, activity_subtype, hora=time(10, 0)):
    from apps.appointments.models import Appointment
    from apps.slots.models import Slot
    s = Slot.objects.create(room=room, date=d, start_time=hora, end_time=time(hora.hour + 1, 0),
                            availability=cupos - reservas, activity_subtype=activity_subtype)
    apps = [Appointment.objects.create(slot=s, person=person) for _ in range(reservas)]
    return s, apps


# --- V09: la lista de espera no se suma a las reservas (HU-17 c.3) -----------
@pytest.mark.django_db
def test_v09_lista_de_espera_no_suma(room, person, activity_subtype):
    from apps.waiting_list.models import WaitingList
    d = _lunes_pasados(1)[0]
    s, _ = _clase(room, d, 7, 7, person, activity_subtype)
    WaitingList.objects.create(slot=s, person=person)
    key = FranjaKey(room.studio_id, room.id, activity_subtype.id, 0, time(10, 0))
    assert build_franjas(d, d + timedelta(days=1))[key] == [1.0]


# --- V10: sedes/salas/subtipos se analizan por separado (HU-17 c.2) ----------
@pytest.mark.django_db
def test_v10_franjas_separadas_por_sala(room, person, activity_subtype):
    from apps.rooms.models import Room
    otra = Room.objects.create(name='Sala 2', studio=room.studio)
    d = _lunes_pasados(1)[0]
    _clase(room, d, 7, 7, person, activity_subtype)
    _clase(otra, d, 7, 0, person, activity_subtype)
    franjas = build_franjas(d, d + timedelta(days=1))
    assert franjas[FranjaKey(room.studio_id, room.id, activity_subtype.id, 0, time(10, 0))] == [1.0]
    assert franjas[FranjaKey(room.studio_id, otra.id, activity_subtype.id, 0, time(10, 0))] == [0.0]


# --- V11: clases dadas de baja (p. ej., por feriado) no son observaciones ----
@pytest.mark.django_db
def test_v11_clase_dada_de_baja_no_cuenta(room, person, activity_subtype):
    d = _lunes_pasados(1)[0]
    s, _ = _clase(room, d, 7, 0, person, activity_subtype)
    s.deleted = d
    s.save()
    assert build_franjas(d, d + timedelta(days=1)) == {}


# --- V12: reserva dada de baja DESPUÉS de la clase (HU-17 c.1) ---------------
@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason=(
    'Diferencia detectada: la ocupación se calcula con las reservas vigentes al '
    'momento del análisis y no con las confirmadas al inicio de la clase. Una baja '
    'posterior (p. ej., remover_personas_vencidas) reduce la ocupación de clases pasadas.'))
def test_v12_baja_posterior_no_altera_clase_pasada(room, person, activity_subtype):
    d = _lunes_pasados(1)[0]
    s, apps = _clase(room, d, 7, 7, person, activity_subtype)
    # baja posterior a la clase, como la hace remover_personas_vencidas
    apps[0].deleted = timezone.now()
    apps[0].save()
    s.availability += 1
    s.save()
    key = FranjaKey(room.studio_id, room.id, activity_subtype.id, 0, time(10, 0))
    assert build_franjas(d, d + timedelta(days=1))[key] == [1.0]   # 7 de 7 al inicio


# --- V13: restricción operativa sin recurso disponible (HU-19 c.1) -----------
@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason=(
    'Diferencia detectada: sin sala compatible libre, la recomendación «add» se '
    'genera igual y solo se marca con la condición pendiente «sin_sala_alternativa».'))
def test_v13_sin_recurso_no_recomienda_apertura(room, person, activity_subtype):
    room.capacity = 5
    room.save()
    for d in _lunes_pasados(8):
        _clase(room, d, 7, 7, person, activity_subtype)   # 7 cupos > capacidad 5: no hay sala apta
    analysis = run_analysis(default_params())
    assert analysis.recommendations.filter(type='add').count() == 0


# --- V14: la restricción de la profesora no se evalúa, se informa ------------
@pytest.mark.django_db
def test_v14_profesora_queda_como_condicion_pendiente(room, person, activity_subtype):
    for d in _lunes_pasados(8):
        _clase(room, d, 7, 7, person, activity_subtype)
    r = run_analysis(default_params()).recommendations.get(type='add')
    assert 'disponibilidad_profesora' in r.pending_conditions


# --- V15: reubicación solo hacia franjas con demanda (HU-19 c.2) -------------
@pytest.mark.django_db
def test_v15_baja_sin_demanda_en_otra_franja_es_revision(room, person, activity_subtype):
    for d in _lunes_pasados(8):
        _clase(room, d, 7, 1, person, activity_subtype)
    recs = run_analysis(default_params()).recommendations
    assert recs.filter(type='reduce').count() == 1
    assert recs.filter(type='relocate').count() == 0


# --- V16: la recomendación expone datos y reglas (HU-19 c.4) -----------------
@pytest.mark.django_db
def test_v16_recomendacion_con_datos_y_reglas(room, person, activity_subtype):
    for d in _lunes_pasados(8):
        _clase(room, d, 7, 7, person, activity_subtype)
    r = run_analysis(default_params()).recommendations.get(type='add')
    assert r.observations_count == 8
    assert r.period_start and r.period_end
    assert r.rules_applied['high_occupancy_threshold'] == 0.8
    assert r.state == 'pending'   # no modifica la programación


# --- V17: subutilizada con lista de espera propia (HU-19 c.3) ----------------
@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason=(
    'Diferencia detectada: la lista de espera de la propia franja no se considera '
    'evidencia para mantener la oferta; se recomienda «reduce» igual.'))
def test_v17_baja_con_lista_de_espera_propia_no_reduce(room, person, activity_subtype):
    from apps.waiting_list.models import WaitingList
    slots = [_clase(room, d, 7, 1, person, activity_subtype)[0] for d in _lunes_pasados(8)]
    WaitingList.objects.create(slot=slots[0], person=person)
    assert run_analysis(default_params()).recommendations.filter(type='reduce').count() == 0


# --- V18: la sala ocupada por una plantilla activa no es un recurso libre (HU-19 c.1) ---
@pytest.mark.django_db
@pytest.mark.xfail(strict=True, reason=(
    'Diferencia detectada: el control de superposición solo mira clases futuras ya '
    'generadas; si la grilla vigente (plantilla) todavía no generó esas clases, '
    'propone como alternativa la misma sala, día y hora que ya están ocupados.'))
def test_v18_plantilla_activa_ocupa_la_sala(room, person, activity_subtype, week):
    from apps.slots.models import SlotTemplate
    t = SlotTemplate.objects.create(start_time=time(10, 0), end_time=time(11, 0), room=room,
                                    activity_subtype=activity_subtype, availability=7)
    t.days_of_week.add(week)   # lunes 10:00, la misma franja analizada
    for d in _lunes_pasados(8):
        _clase(room, d, 7, 7, person, activity_subtype)
    r = run_analysis(default_params()).recommendations.get(type='add')
    assert r.proposed_alternative is None
