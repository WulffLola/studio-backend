import pytest
from datetime import date, timedelta
from unittest import mock
from django.core.management import call_command
from apps.people.models import Person, PersonActivePlan


# Helper: Person.latest_coverage_end()

@pytest.mark.django_db
class TestLatestCoverageEnd:
    def test_none_sin_cobertura(self):
        p = Person.objects.create(name='A', last_name='B', dni='70000000')
        assert p.latest_coverage_end() is None

    def test_solo_exp_date_prueba(self):
        d = date.today() - timedelta(days=2)
        p = Person.objects.create(name='A', last_name='B', dni='70000001', exp_date=d)
        assert p.latest_coverage_end() == d

    def test_solo_plan(self, plans_subtype_a):
        p = Person.objects.create(name='A', last_name='B', dni='70000002')
        d = date.today() + timedelta(days=10)
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=d, sessions_total=8, sessions_remaining=8,
        )
        assert p.latest_coverage_end() == d

    def test_ambos_gana_el_mayor(self, plans_subtype_a):
        p = Person.objects.create(
            name='A', last_name='B', dni='70000003',
            exp_date=date.today() - timedelta(days=30),
        )
        plan_d = date.today() + timedelta(days=5)
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=plan_d, sessions_total=8, sessions_remaining=8,
        )
        assert p.latest_coverage_end() == plan_d

    def test_plan_soft_deleted_ignorado(self, plans_subtype_a):
        exp_prueba = date.today() - timedelta(days=30)
        p = Person.objects.create(name='A', last_name='B', dni='70000004', exp_date=exp_prueba)
        plan = PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=5), sessions_total=8, sessions_remaining=8,
        )
        plan.deleted = date.today()
        plan.save()
        # Con el plan soft-deleted, la única cobertura viva es el exp_date de prueba.
        assert p.latest_coverage_end() == exp_prueba


# Command: remover_personas_vencidas

@pytest.mark.django_db
class TestRemoverPersonasVencidas:
    def _run(self):
        with mock.patch('requests.post') as post:
            post.return_value.raise_for_status.return_value = None
            call_command('remover_personas_vencidas')
        return post

    def test_pagante_vencido_mas_de_7_dias_se_da_de_baja(self, plans_subtype_a):
        p = Person.objects.create(name='Pag', last_name='X', dni='71000000', phone='111')
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=date.today() - timedelta(days=8), sessions_total=8, sessions_remaining=3,
        )
        self._run()
        p.refresh_from_db()
        assert p.deleted is not None
        assert not p.active_plans.exists()  # sus planes quedaron soft-deleted

    def test_pagante_con_plan_vigente_no_se_da_de_baja(self, plans_subtype_a):
        p = Person.objects.create(name='Pag', last_name='X', dni='71000001', phone='111')
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=20), sessions_total=8, sessions_remaining=3,
        )
        self._run()
        p.refresh_from_db()
        assert p.deleted is None

    def test_pagante_renovado_no_se_da_de_baja(self, plans_subtype_a):
        """Plan viejo vencido + plan nuevo vigente: gana el nuevo (max), no se da de baja."""
        p = Person.objects.create(name='Pag', last_name='X', dni='71000002', phone='111')
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=date.today() - timedelta(days=40), sessions_total=8, sessions_remaining=0,
        )
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=date.today() + timedelta(days=10), sessions_total=8, sessions_remaining=8,
        )
        self._run()
        p.refresh_from_db()
        assert p.deleted is None

    def test_prueba_vencida_se_da_de_baja(self):
        """Comportamiento previo intacto: persona de prueba (solo Person.exp_date) vencida +7d."""
        p = Person.objects.create(
            name='Prb', last_name='X', dni='71000003', phone='111',
            exp_date=date.today() - timedelta(days=10),
        )
        self._run()
        p.refresh_from_db()
        assert p.deleted is not None

    def test_dentro_de_gracia_no_se_da_de_baja(self):
        p = Person.objects.create(
            name='Prb', last_name='X', dni='71000004', phone='111',
            exp_date=date.today() - timedelta(days=3),
        )
        self._run()
        p.refresh_from_db()
        assert p.deleted is None

    def test_mensaje_pagante_vs_prueba(self, plans_subtype_a):
        pag = Person.objects.create(name='Pag', last_name='X', dni='71000005', phone='111')
        PersonActivePlan.objects.create(
            person=pag, plans_subtype=plans_subtype_a,
            exp_date=date.today() - timedelta(days=8), sessions_total=8, sessions_remaining=1,
        )
        prb = Person.objects.create(
            name='Prb', last_name='Y', dni='71000006', phone='222',
            exp_date=date.today() - timedelta(days=8),
        )
        post = self._run()
        mensajes = {c.kwargs['json']['number']: c.kwargs['json']['message'] for c in post.call_args_list}
        assert 'servicios han sido dados de baja' in mensajes['111']
        assert 'turnos de prueba' in mensajes['222']


# Command: enviar_mensaje_por_vencer

@pytest.mark.django_db
class TestEnviarMensajePorVencer:
    def _run(self):
        with mock.patch('requests.post') as post:
            post.return_value.raise_for_status.return_value = None
            call_command('enviar_mensaje_por_vencer')
        return post

    def test_plan_vence_en_3_dias_notifica(self, plans_subtype_a):
        from django.utils import timezone
        p = Person.objects.create(name='Pag', last_name='X', dni='72000000', phone='111')
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=timezone.now().date() + timedelta(days=3), sessions_total=8, sessions_remaining=8,
        )
        post = self._run()
        assert post.call_count == 1

    def test_cobertura_mas_larga_no_notifica(self, plans_subtype_a):
        """Un plan vence en 3 días pero otro más tarde: gana el más tarde (max), no notifica."""
        from django.utils import timezone
        today = timezone.now().date()
        p = Person.objects.create(name='Pag', last_name='X', dni='72000001', phone='111')
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=today + timedelta(days=3), sessions_total=8, sessions_remaining=8,
        )
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=today + timedelta(days=15), sessions_total=8, sessions_remaining=8,
        )
        post = self._run()
        assert post.call_count == 0

    def test_prueba_vence_en_3_dias_notifica(self):
        from django.utils import timezone
        p = Person.objects.create(
            name='Prb', last_name='X', dni='72000002', phone='111',
            exp_date=timezone.now().date() + timedelta(days=3),
        )
        post = self._run()
        assert post.call_count == 1

    def test_fecha_en_mensaje_formato_dd_mm_yyyy(self, plans_subtype_a):
        """ la fecha del recordatorio va en dd/mm/yyyy, no en yyyy-mm-dd."""
        from django.utils import timezone
        # Se usa la misma referencia que el comando (timezone.now().date()) para que
        # la ventana de 3 días matchee sin depender del offset de TZ (date.today()
        # puede diferir en un día). vio el mismo flake.
        venc = timezone.now().date() + timedelta(days=3)
        p = Person.objects.create(name='Pag', last_name='X', dni='72000003', phone='111')
        PersonActivePlan.objects.create(
            person=p, plans_subtype=plans_subtype_a,
            exp_date=venc, sessions_total=8, sessions_remaining=8,
        )
        post = self._run()
        assert post.call_count == 1
        message = post.call_args.kwargs['json']['message']
        assert venc.strftime('%d/%m/%Y') in message          # 29/08/2026
        assert venc.strftime('%Y-%m-%d') not in message       # no ISO
        assert venc.isoformat() not in message
        # No se toca el valor almacenado
        p.refresh_from_db()
        assert p.active_plans.first().exp_date == venc
