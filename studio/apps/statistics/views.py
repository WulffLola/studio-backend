
from rest_framework import viewsets
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper
from rest_framework import viewsets, status
from rest_framework.response import Response
from datetime import datetime, timedelta
from apps.payments.models import Payment, PaymentItem
from apps.expenses.models import Expense
from apps.expense_type.models import ExpenseType
from apps.appointments.models import Appointment
from apps.activity_subtype.models import ActivitySubType
from django.db.models import Sum
from apps.people.models import Person, PersonActivePlan
from django.db.models.functions import TruncMonth
from django.db.models import Avg, F, ExpressionWrapper, fields, Case, When, IntegerField
from django.db.models import Count, Q
from apps.waiting_list.models import WaitingList
from apps.actions.models import Action
from apps.slots.models import Slot
from django.utils import timezone
from apps.studios.filters import StudioNoticeMixin, resolve_studios

# 0=Lunes … 6=Domingo (coincide con date.weekday())
WEEKDAY_NAMES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _parse_studio(request):
    """Filtro opcional por estudio, unificado con el helper común de
    apps/studios/filters.py: uno o varios estudios (?studio=1,2 o
    ?studio=1&studio=2), formato inválido -> 400, inexistente -> 404 (los errores
    se levantan como excepciones de DRF). Devuelve (studio_ids|None, None):
    None = sin filtro, todos los estudios. Guarda los estudios en
    request.studio_filter para que StudioNoticeMixin avise si alguno está dado
    de baja. El segundo valor se mantiene por compatibilidad (siempre None)."""
    studios = resolve_studios(request)
    request.studio_filter = studios
    if studios is None:
        return None, None
    return [s.pk for s in studios], None


class GrossMarginViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # Obtener start_date y end_date de los parámetros de consulta
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            return Response(
                {"detail": "Ambos 'start_date' y 'end_date' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Utiliza YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date > end_date:
            return Response(
                {"detail": "'start_date' debe ser antes de 'end_date'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Pagos y gastos en el rango (opcionalmente filtrados por estudio)
        payments = Payment.objects.filter(date__gte=start_datetime, date__lte=end_datetime)
        expenses = Expense.objects.filter(date__gte=start_datetime, date__lte=end_datetime)
        if studio_ids is not None:
            payments = payments.filter(studio_id__in=studio_ids)
            expenses = expenses.filter(studio_id__in=studio_ids)
        total_income = float(payments.aggregate(t=Sum('amount'))['t'] or 0)
        total_expenses = float(expenses.aggregate(t=Sum('amount'))['t'] or 0)

        # Calcular el margen bruto
        gross_margin = total_income - total_expenses

        return Response({
            "total_income": total_income,
            "total_expenses": total_expenses,
            "gross_margin": gross_margin
        }, status=status.HTTP_200_OK)

class NetMarginViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # Obtener start_date y end_date de los parámetros de consulta
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            return Response(
                {"detail": "Ambos 'start_date' y 'end_date' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Utiliza YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date > end_date:
            return Response(
                {"detail": "'start_date' debe ser antes de 'end_date'."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())


        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Pagos y sueldos en el rango (opcionalmente filtrados por estudio)
        payments = Payment.objects.filter(date__gte=start_datetime, date__lte=end_datetime)
        salary_expenses = Expense.objects.filter(
            date__gte=start_datetime, date__lte=end_datetime, type__name__icontains="Sueldo"
        )
        if studio_ids is not None:
            payments = payments.filter(studio_id__in=studio_ids)
            salary_expenses = salary_expenses.filter(studio_id__in=studio_ids)
        total_income = float(payments.aggregate(t=Sum('amount'))['t'] or 0)
        total_salaries = float(salary_expenses.aggregate(t=Sum('amount'))['t'] or 0)

        # Calcular el margen neto
        net_margin = total_income - total_salaries

        return Response({
            "total_income": total_income,
            "total_salaries": total_salaries,
            "net_margin": net_margin
        }, status=status.HTTP_200_OK)


class ExpensesByTypeViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # Obtener start_date y end_date de los parámetros de consulta
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            return Response(
                {"detail": "Los campos 'start_date' y 'end_date' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Utiliza YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date > end_date:
            return Response(
                {"detail": "'start_date' debe ser antes de 'end_date'."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())


        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Tipos de gasto (categorías). Filtro opcional por categoría.
        expense_types = ExpenseType.objects.all()
        type_raw = request.query_params.get('expense_type')
        if type_raw:
            try:
                expense_types = expense_types.filter(id=int(type_raw))
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'expense_type' debe ser un id numérico."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Crear una lista para almacenar los totales de cada tipo
        expenses_summary = []

        # Base de gastos del rango (opcionalmente filtrada por estudio)
        base_expenses = Expense.objects.filter(date__gte=start_datetime, date__lte=end_datetime)
        if studio_ids is not None:
            base_expenses = base_expenses.filter(studio_id__in=studio_ids)

        # Iterar sobre cada tipo de gasto y calcular el total en el rango de fechas
        for expense_type in expense_types:
            total_expenses = base_expenses.filter(
                type=expense_type
            ).aggregate(
                total=Sum('amount')
            )['total']
            total_expenses = float(total_expenses or 0)

            expenses_summary.append({
                "expense_type": expense_type.name,
                "total_expenses": total_expenses
            })

        return Response(expenses_summary, status=status.HTTP_200_OK)
    
    
class ClientsStatusViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Alumnos activos (no eliminados) e inactivos (soft-deleted).

    Filtros opcionales: studio (sede donde el alumno tiene turnos), activity
    (plans_subtype.activity_subtype de sus planes), plan (plans_subtype). Se usa
    distinct() para no contar dos veces a un alumno con varios planes/turnos.
    Solo lectura.
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request, *args, **kwargs):
        studio_ids, err = _parse_studio(request)
        if err:
            return err
        activity_raw = request.query_params.get('activity')
        plan_raw = request.query_params.get('plan')
        try:
            activity_id = int(activity_raw) if activity_raw else None
            plan_id = int(plan_raw) if plan_raw else None
        except (TypeError, ValueError):
            return Response(
                {"detail": "Los parámetros 'activity' y 'plan' deben ser ids numéricos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def apply_filters(qs):
            if studio_ids is not None:
                qs = qs.filter(appointments__slot__room__studio_id__in=studio_ids)
            if activity_id is not None:
                qs = qs.filter(active_plans__plans_subtype__activity_subtype_id=activity_id)
            if plan_id is not None:
                qs = qs.filter(active_plans__plans_subtype_id=plan_id)
            return qs.distinct()

        # all_objects: `objects` (DeletedManager) ya excluye los eliminados, así que
        # filtrar deleted__isnull=False sobre él daba siempre 0 (bug previo).
        active_clients = apply_filters(Person.all_objects.filter(deleted__isnull=True))
        inactive_clients = apply_filters(Person.all_objects.filter(deleted__isnull=False))

        return Response({
            "total_active_clients": active_clients.count(),
            "active_clients": list(active_clients.values("name", "last_name", "phone")),
            "total_inactive_clients": inactive_clients.count(),
            "inactive_clients": list(inactive_clients.values("name", "last_name", "phone")),
        }, status=status.HTTP_200_OK)
        

class ClientsByMonthViewSet(viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # all_objects: incluye eliminados para poder contar bajas. `objects`
        # (DeletedManager) excluye deleted -> cancellations daba siempre 0.
        clients = Person.all_objects.all()

        # Altas por mes (por fecha de creación).
        new_rows = clients.annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            total_new_clients=Count('id')
        ).order_by('month')

        # Bajas por mes (por fecha de baja).
        cancel_rows = clients.filter(deleted__isnull=False).annotate(
            month=TruncMonth('deleted')
        ).values('month').annotate(
            total_cancellations=Count('id')
        ).order_by('month')

        def _fmt(month):
            return month.strftime('%Y-%m') if month else None

        new_clients_by_month = [
            {"month": _fmt(r['month']), "total_new_clients": r['total_new_clients']}
            for r in new_rows
        ]
        cancellations_by_month = [
            {"month": _fmt(r['month']), "total_cancellations": r['total_cancellations']}
            for r in cancel_rows
        ]

        # Crecimiento neto por mes = altas − bajas.
        net = {}
        for r in new_clients_by_month:
            net[r['month']] = net.get(r['month'], 0) + r['total_new_clients']
        for r in cancellations_by_month:
            net[r['month']] = net.get(r['month'], 0) - r['total_cancellations']
        net_growth_by_month = [
            {"month": m, "net_growth": v} for m, v in sorted(net.items(), key=lambda kv: (kv[0] is None, kv[0]))
        ]

        return Response({
            "new_clients_by_month": new_clients_by_month,
            "cancellations_by_month": cancellations_by_month,
            "net_growth_by_month": net_growth_by_month,
            # Nota: reactivaciones y motivos de alta/baja requieren un historial
            # que el sistema no guarda aún (ver card.
        }, status=status.HTTP_200_OK)
    

class RetentionRateViewSet(viewsets.ViewSet):
    """Renovaciones de planes.

    Antes contaba 'personas con más de un pago', que no refleja renovaciones.
    Ahora: un plan se considera RENOVADO si el siguiente plan contratado del mismo
    alumno y actividad (plans_subtype.activity_subtype), ordenado por created_at,
    cae dentro de `exp_date + window_days`. La tasa se calcula solo sobre los
    planes cuyo plazo de renovación ya venció (exp_date + window_days < hoy), para
    no contar como 'no renovados' a los que todavía están en plazo. Solo lectura.

    Param: window_days (opcional, default 30).
    Nota: PersonActivePlan no tiene vínculo a estudio -> sin filtro por estudio.
    Los planes con created_at nulo (históricos previos a no pueden
    vincularse como 'siguiente' y se omiten de ese rol.
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        raw_window = request.query_params.get('window_days', '30')
        try:
            window_days = int(raw_window)
            if window_days <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'window_days' debe ser un entero positivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.now().date()
        window = timedelta(days=window_days)

        plans = (
            PersonActivePlan.objects
            .filter(deleted__isnull=True)
            # Se excluyen los planes con created_at NULL: no pueden ordenarse ni
            # vincularse como 'siguiente', así que nunca podrían marcarse como
            # renovados y subestimarían la tasa. OJO: al migrar datos históricos
            # (p.ej. Aura) hay que poblar created_at para que entren al cálculo.
            .filter(created_at__isnull=False)
            .select_related('plans_subtype')
            .order_by('created_at', 'id')
        )

        # Agrupar por (alumno, actividad) manteniendo el orden de contratación.
        from collections import defaultdict
        groups = defaultdict(list)
        for p in plans:
            activity_id = p.plans_subtype.activity_subtype_id if p.plans_subtype_id else None
            groups[(p.person_id, activity_id)].append(p)

        eligible = 0
        renewed = 0
        for group in groups.values():
            for i, p in enumerate(group):
                # Elegible solo si su plazo de renovación ya terminó.
                if not (p.exp_date + window < today):
                    continue
                eligible += 1
                # El 'siguiente' plan contratado del grupo.
                nxt = group[i + 1] if i + 1 < len(group) else None
                if nxt and nxt.created_at and nxt.created_at.date() <= p.exp_date + window:
                    renewed += 1

        renewal_rate = round(renewed / eligible * 100, 2) if eligible > 0 else 0

        return Response({
            "window_days": window_days,
            "eligible_plans": eligible,
            "renewed_plans": renewed,
            "renewal_rate": renewal_rate,
        }, status=status.HTTP_200_OK)
        
        
class ClientsByPlanViewSet(viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # Agrupar por plans_subtype (via PersonActivePlan) y contar alumnos distintos.
        clients_by_plan = (
            PersonActivePlan.objects
            .filter(deleted__isnull=True, person__deleted__isnull=True)
            .values('plans_subtype__name')
            .annotate(total_clients=Count('person', distinct=True))
            .order_by('plans_subtype__name')
        )
        return Response(clients_by_plan, status=status.HTTP_200_OK)
    
class PeakHoursViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        studio_ids, err = _parse_studio(request)
        if err:
            return err
        qs = WaitingList.objects.all()
        if studio_ids is not None:
            qs = qs.filter(slot__room__studio_id__in=studio_ids)
        # Agrupar por horario (start_time del slot) y contar cuántas personas
        # están en lista de espera. 'slot__time_slot' no existe; el
        # campo del Slot es start_time.)
        peak_hours = qs.values('slot__start_time').annotate(
            total_waiting=Count('id')
        ).order_by('-total_waiting')

        return Response(peak_hours, status=status.HTTP_200_OK)
    
class AverageAgeViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Edad promedio y distribución por rangos de los alumnos activos.

    Calcula la edad real desde birth_date (no solo la resta de años) y cuenta
    alumnos únicos en cada rango. Filtros opcionales: studio (sede con turnos) y
    activity (plans_subtype.activity_subtype) y start_time (HH:MM[:SS], horario
    del turno reservado). Solo lectura.
    """
    permission_classes = [IsAdministrador | IsSuper]

    RANGES = ['<18', '18-29', '30-44', '45-59', '60+']

    @staticmethod
    def _bucket(age):
        if age < 18:
            return '<18'
        if age < 30:
            return '18-29'
        if age < 45:
            return '30-44'
        if age < 60:
            return '45-59'
        return '60+'

    def list(self, request, *args, **kwargs):
        studio_ids, err = _parse_studio(request)
        if err:
            return err
        activity_raw = request.query_params.get('activity')
        try:
            activity_id = int(activity_raw) if activity_raw else None
        except (TypeError, ValueError):
            return Response({"detail": "El parámetro 'activity' debe ser un id numérico."},
                            status=status.HTTP_400_BAD_REQUEST)

        start_time_raw = request.query_params.get('start_time')
        start_time = None
        if start_time_raw:
            for fmt in ('%H:%M', '%H:%M:%S'):
                try:
                    start_time = datetime.strptime(start_time_raw, fmt).time()
                    break
                except ValueError:
                    continue
            if start_time is None:
                return Response({"detail": "El parámetro 'start_time' debe tener formato HH:MM o HH:MM:SS."},
                                status=status.HTTP_400_BAD_REQUEST)

        people = Person.all_objects.filter(deleted__isnull=True, birth_date__isnull=False)
        # studio y start_time en UN solo filter() sobre la relación multivaluada
        # appointments: deben cumplirse en la MISMA cita (no en dos joins
        # independientes). Solo reservas activas.
        appt_kwargs = {}
        if studio_ids is not None:
            appt_kwargs['appointments__slot__room__studio_id__in'] = studio_ids
        if start_time is not None:
            appt_kwargs['appointments__slot__start_time'] = start_time
        if appt_kwargs:
            appt_kwargs['appointments__deleted__isnull'] = True
            people = people.filter(**appt_kwargs)
        if activity_id is not None:
            people = people.filter(active_plans__plans_subtype__activity_subtype_id=activity_id)
        people = people.distinct()

        today = timezone.now().date()
        ranges = {r: 0 for r in self.RANGES}
        total = 0
        age_sum = 0
        # Se pide (id, birth_date): con solo birth_date, distinct() colapsaría a
        # alumnos distintos que comparten fecha de nacimiento.
        for _pid, birth_date in people.values_list('pk', 'birth_date'):
            age = today.year - birth_date.year - (
                (today.month, today.day) < (birth_date.month, birth_date.day)
            )
            ranges[self._bucket(age)] += 1
            age_sum += age
            total += 1

        average_age = round(age_sum / total, 2) if total else None
        return Response({
            "average_age": average_age,
            "total": total,
            "ranges": ranges,
        }, status=status.HTTP_200_OK)


class AverageAgeByHourViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        today = datetime.now().date()

        # Calcular la edad de cada persona simplemente restando el año de nacimiento
        age_expression = ExpressionWrapper(
            today.year - F('birth_date__year'),
            output_field=IntegerField()
        )

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Un solo filter() para que sea UN solo join a appointments (si no, el
        # AVG se calcula sobre el producto cartesiano de citas).
        people_filter = dict(deleted__isnull=True, appointments__slot__isnull=False)
        if studio_ids is not None:
            people_filter['appointments__slot__room__studio_id__in'] = studio_ids
        base_people = Person.objects.filter(**people_filter)

        # Promedio de edad por horario (start_time del slot).
        # 'slot__time_slot' no existe; el campo del Slot es start_time.)
        average_age_by_hour = base_people.annotate(
            age=age_expression
        ).values('appointments__slot__start_time').annotate(
            average_age=Avg('age')
        ).order_by('appointments__slot__start_time')

        return Response(average_age_by_hour, status=status.HTTP_200_OK)
    
class MostProfitablePlanViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper]
    
   
    def list(self, request, *args, **kwargs):
        # Obtener los parámetros de fecha del request
        year = request.query_params.get('year')  # Formato esperado: 'YYYY'
        month = request.query_params.get('month')  # Opcional: 'MM'

        if not year:
            return Response({"detail": "El parámetro 'year' es obligatorio y debe tener el formato 'YYYY'."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            # Convertir el año a un entero y establecer el rango de fechas inicial
            year = int(year)
            start_date = datetime(year=year, month=1, day=1).date()
            end_date = datetime(year=year, month=12, day=31).date()

            # Si se pasa el parámetro 'month', ajustar el rango al mes especificado
            if month:
                month = int(month)
                start_date = datetime(year=year, month=month, day=1).date()
                if month == 12:
                    end_date = datetime(year=year + 1, month=1, day=1).date() - timedelta(days=1)
                else:
                    end_date = datetime(year=year, month=month + 1, day=1).date() - timedelta(days=1)

        except ValueError:
            return Response({"detail": "Formato inválido para 'year' o 'month'. Use 'YYYY' para el año y 'MM' para el mes."},
                            status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Sumar los ingresos por plans_subtype usando PaymentItem.final_amount
        # (fuente de verdad del monto por plan en el modelo multi-plan).
        items = PaymentItem.objects.filter(
            payment__date__gte=start_date, payment__date__lte=end_date,
            payment__deleted__isnull=True, deleted__isnull=True,
        )
        if studio_ids is not None:
            items = items.filter(payment__studio_id__in=studio_ids)
        plan_profitability = (
            items
            .values('plans_subtype__name')
            .annotate(total_income=Sum('final_amount'))
            .order_by('-total_income')
        )

        if not plan_profitability.exists():
            return Response({"detail": "No se encontraron datos para el rango de fechas especificado."},
                            status=status.HTTP_404_NOT_FOUND)

        # Ranking completo por ingresos (además del plan más rentable).
        ranking = list(plan_profitability)
        most_profitable_plan = ranking[0]

        return Response({
            "most_profitable_plan": most_profitable_plan,
            "ranking": ranking,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            }
        }, status=status.HTTP_200_OK)
    
class CancellationRateByMonthViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Cancelaciones de RESERVAS (Appointment) en el período.

    Antes contaba Personas dadas de baja (Person.deleted), que no tiene nada que
    ver con cancelaciones de reservas. Ahora mide, sobre las reservas cuyas clases
    (slot) caen en el mes:
      - tasa de cancelación = canceladas / total de reservas del período,
      - efecto sobre el saldo (cuántas devolvieron sesión del plan),
      - anticipación de la cancelación (slot − deleted) en horas + buckets,
      - reubicaciones (update de turno) contadas APARTE, nunca como cancelación.
    Solo lectura; no modifica datos. Param: month=YYYY-MM (requerido), studio opcional.
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        month = request.query_params.get('month')  # Formato esperado: 'YYYY-MM'
        if not month:
            return Response({"detail": "El parámetro 'month' es obligatorio y debe tener el formato 'YYYY-MM'."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            start_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
        except ValueError:
            return Response({"detail": "Formato inválido para el parámetro 'month'. Use 'YYYY-MM'."},
                            status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Reservas cuyas clases (slot) caen en el período, vivas + canceladas.
        reservations = Appointment.all_objects.filter(
            slot__date__gte=start_date, slot__date__lte=end_date,
        )
        if studio_ids is not None:
            reservations = reservations.filter(slot__room__studio_id__in=studio_ids)

        total = reservations.count()
        cancelled_qs = reservations.filter(deleted__isnull=False)
        cancelled = cancelled_qs.count()
        rate = (cancelled / total * 100) if total > 0 else 0

        # Efecto sobre el saldo: canceladas que devolvieron una sesión del plan.
        sessions_returned = cancelled_qs.filter(consumed_plan__isnull=False).count()

        # Anticipación = inicio de la clase (slot date+start_time) − momento de la
        # cancelación (deleted), en horas. Buckets según el umbral de 2h.
        lt_2h = h2_24 = gt_24h = 0
        total_hours = 0.0
        counted = 0
        for appt in cancelled_qs.select_related('slot'):
            slot = appt.slot
            if not slot or not slot.date or not slot.start_time or not appt.deleted:
                continue
            slot_dt = timezone.make_aware(datetime.combine(slot.date, slot.start_time))
            anticipation = (slot_dt - appt.deleted).total_seconds() / 3600
            if anticipation < 2:
                lt_2h += 1
            elif anticipation < 24:
                h2_24 += 1
            else:
                gt_24h += 1
            total_hours += anticipation
            counted += 1
        average_hours = round(total_hours / counted, 2) if counted else 0

        # Reubicaciones (update de turno) del período, contadas por separado.
        reassignments = Action.objects.filter(
            action="Actualizar", target="Turno",
            timestamp__date__gte=start_date, timestamp__date__lte=end_date,
        ).count()

        return Response({
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "total_reservations": total,
            "cancelled_reservations": cancelled,
            "cancellation_rate": round(rate, 2),
            "sessions_returned": sessions_returned,
            "anticipation": {
                "average_hours": average_hours,
                "buckets": {"lt_2h": lt_2h, "h2_24": h2_24, "gt_24h": gt_24h},
            },
            "reassignments": reassignments,
        }, status=status.HTTP_200_OK)
        
class PaymentStatusForCurrentMonthViewSet(StudioNoticeMixin, viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # Obtener el mes actual
        today = datetime.now().date()
        start_date = today.replace(day=1)
        end_date = today.replace(month=today.month % 12 + 1, day=1) if today.month != 12 else today.replace(year=today.year + 1, month=1, day=1)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        # Personas que ya pagaron este mes (opcionalmente en un estudio)
        paid_filter = dict(
            payment__date__gte=start_date, payment__date__lt=end_date,
            deleted__isnull=True,
        )
        if studio_ids is not None:
            paid_filter['payment__studio_id__in'] = studio_ids
        people_who_paid = Person.objects.filter(**paid_filter).distinct()
        people_who_paid_data = people_who_paid.values("name", "last_name", "phone")

        # Personas que no pagaron este mes
        people_who_didnt_pay = Person.objects.filter(
            deleted__isnull=True
        ).exclude(id__in=people_who_paid)
        people_who_didnt_pay_data = people_who_didnt_pay.values("name", "last_name", "phone")

        # Retornar la respuesta con cantidad y lista
        return Response({
            "people_who_paid_count": people_who_paid.count(),
            "people_who_paid": list(people_who_paid_data),
            "people_who_didnt_pay_count": people_who_didnt_pay.count(),
            "people_who_didnt_pay": list(people_who_didnt_pay_data)
        }, status=status.HTTP_200_OK)


class StudioStatsViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """
    Estadísticas generales por estudio.
    Query params: studio (requerido), start_date, end_date (YYYY-MM-DD).
    """
    permission_classes = [IsAdministrador | IsSuper]

    def _parse_date_range(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
            end_dt = datetime.combine(datetime.strptime(end_date, '%Y-%m-%d').date(), datetime.max.time()) if end_date else None
        except ValueError:
            return None, None, Response(
                {"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return start_dt, end_dt, None

    def list(self, request, *args, **kwargs):
        studio_id = request.query_params.get('studio')
        if not studio_id:
            return Response({"detail": "El parámetro 'studio' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        # validación común (400/404) y uno o varios estudios.
        studio_ids, _ = _parse_studio(request)

        start_dt, end_dt, err = self._parse_date_range(request)
        if err:
            return err

        payments_qs = Payment.objects.filter(studio_id__in=studio_ids, deleted__isnull=True)
        expenses_qs = Expense.objects.filter(studio_id__in=studio_ids, deleted__isnull=True)
        appointments_qs = Appointment.objects.filter(slot__room__studio_id__in=studio_ids, deleted__isnull=True)

        if start_dt:
            payments_qs = payments_qs.filter(date__gte=start_dt)
            expenses_qs = expenses_qs.filter(date__gte=start_dt)
            appointments_qs = appointments_qs.filter(slot__date__gte=start_dt.date())
        if end_dt:
            payments_qs = payments_qs.filter(date__lte=end_dt)
            expenses_qs = expenses_qs.filter(date__lte=end_dt)
            appointments_qs = appointments_qs.filter(slot__date__lte=end_dt.date())

        total_income = float(payments_qs.aggregate(total=Sum('amount'))['total'] or 0)
        total_expenses = float(expenses_qs.aggregate(total=Sum('amount'))['total'] or 0)

        active_people_ids = appointments_qs.values_list('person_id', flat=True).distinct()

        return Response({
            "studio_id": studio_id,   # valor recibido, sin cambios
            "studio": studio_ids,     # ids filtrados
            "total_income": total_income,
            "total_expenses": total_expenses,
            "gross_margin": total_income - total_expenses,
            "total_payments": payments_qs.count(),
            "total_appointments": appointments_qs.count(),
            "unique_active_clients": active_people_ids.count(),
        }, status=status.HTTP_200_OK)


class PersonStatsViewSet(viewsets.ViewSet):
    """
    Estadísticas por persona/cliente.
    Query param: person (requerido).
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request, *args, **kwargs):
        person_id = request.query_params.get('person')
        if not person_id:
            return Response({"detail": "El parámetro 'person' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            person = Person.objects.get(pk=person_id)
        except Person.DoesNotExist:
            return Response({"detail": "Persona no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        payments = Payment.objects.filter(person=person, deleted__isnull=True).order_by('-date')
        total_paid = float(payments.aggregate(total=Sum('amount'))['total'] or 0)

        last_payment = payments.first()

        appointments = Appointment.objects.filter(person=person, deleted__isnull=True)
        total_appointments = appointments.count()
        today = datetime.now().date()
        upcoming_appointments = appointments.filter(slot__date__gte=today).count()
        # Entrenamientos realizados = citas cuyo slot ya pasó (slot__date < hoy),
        # no eliminadas. No hay flag de asistencia en el modelo.
        completed_appointments = appointments.filter(slot__date__lt=today).count()

        from apps.slots.models import FixedSlot
        fixed_slots = FixedSlot.objects.filter(person=person, deleted__isnull=True).select_related('template').values(
            'id', 'template__start_time', 'template__end_time', 'start_date', 'end_date', 'observation'
        )

        # Último plan del alumno = último PersonActivePlan (modelo nuevo).
        last_active = (
            PersonActivePlan.all_objects
            .filter(person=person)
            .order_by('-id')
            .first()
        )
        current_plan = None
        if last_active:
            current_plan = {
                "id": last_active.id,
                "plans_subtype": last_active.plans_subtype.name if last_active.plans_subtype_id else None,
            }

        return Response({
            "person_id": person.id,
            "name": f"{person.name} {person.last_name}",
            "is_active": person.deleted is None,
            "total_paid": total_paid,
            "total_payments": payments.count(),
            "last_payment_date": last_payment.date.isoformat() if last_payment and last_payment.date else None,
            "total_appointments": total_appointments,
            "upcoming_appointments": upcoming_appointments,
            "completed_appointments": completed_appointments,
            "current_plan": current_plan,
            "fixed_slots": list(fixed_slots),
        }, status=status.HTTP_200_OK)


class ActivitySubtypeStatsViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """
    Estadísticas por sub-actividad.
    Query params: start_date, end_date (YYYY-MM-DD, opcionales).
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        appointments_qs = Appointment.objects.filter(
            deleted__isnull=True,
            slot__activity_subtype__isnull=False,
        )
        if start_date:
            appointments_qs = appointments_qs.filter(slot__date__gte=start_date)
        if end_date:
            appointments_qs = appointments_qs.filter(slot__date__lte=end_date)
        if studio_ids is not None:
            appointments_qs = appointments_qs.filter(slot__room__studio_id__in=studio_ids)

        appt_by_subtype = (
            appointments_qs
            .values('slot__activity_subtype', 'slot__activity_subtype__name')
            .annotate(total_appointments=Count('id'))
            .order_by('-total_appointments')
        )

        # Revenue per subtype via PaymentItems
        items_qs = PaymentItem.objects.filter(
            deleted__isnull=True,
            plans_subtype__activity_subtype__isnull=False,
        )
        if start_date:
            items_qs = items_qs.filter(payment__date__date__gte=start_date)
        if end_date:
            items_qs = items_qs.filter(payment__date__date__lte=end_date)
        if studio_ids is not None:
            items_qs = items_qs.filter(payment__studio_id__in=studio_ids)

        revenue_by_subtype = {
            row['plans_subtype__activity_subtype']: row['total_revenue']
            for row in items_qs.values('plans_subtype__activity_subtype').annotate(
                total_revenue=Sum('final_amount')
            )
        }

        result = [
            {
                "activity_subtype_id": row['slot__activity_subtype'],
                "activity_subtype_name": row['slot__activity_subtype__name'],
                "total_appointments": row['total_appointments'],
                "total_revenue": float(revenue_by_subtype.get(row['slot__activity_subtype'], 0) or 0),
            }
            for row in appt_by_subtype
        ]

        return Response(result, status=status.HTTP_200_OK)

# Umbrales de recurrencia de ocupación (fracción de la capacidad de la clase).
HIGH_OCCUPANCY_THRESHOLD = 0.8
LOW_OCCUPANCY_THRESHOLD = 0.5


class OccupancyByHourViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Ocupación por franja horaria.

    Agrupa los slots (no eliminados) del rango por estudio, sala, actividad, día
    de la semana y hora. Por slot: confirmadas = Appointments vivas; cupos =
    (availability remanente) + confirmadas, lo que reconstruye el cupo inicial.
    Por grupo devuelve ocupación (Σ confirmadas ÷ Σ cupos), % de clases llenas y
    la recurrencia (cantidad de clases). Ordenado por ocupación desc para ver de
    una las franjas de mayor y menor ocupación. Solo lectura.

    Params: start_date, end_date (YYYY-MM-DD, opcionales), studio (opcional).
    Nota: usa el estado actual reconstruido, no un snapshot histórico (ver #11).
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        slots = (
            Slot.objects
            .filter(date__isnull=False, start_time__isnull=False)
            .select_related('room', 'activity_subtype')
        )
        if start_date:
            slots = slots.filter(date__gte=start_date)
        if end_date:
            slots = slots.filter(date__lte=end_date)
        if studio_ids is not None:
            slots = slots.filter(room__studio_id__in=studio_ids)
        slots = slots.annotate(
            confirmed=Count('appointments', filter=Q(appointments__deleted__isnull=True))
        )

        groups = {}
        for s in slots:
            confirmed = s.confirmed or 0
            cupos = (s.availability or 0) + confirmed
            weekday = s.date.weekday()
            key = (
                s.room.studio_id if s.room else None,
                s.room_id, s.room.name if s.room else None,
                s.activity_subtype_id, s.activity_subtype.name if s.activity_subtype else None,
                weekday, s.start_time,
            )
            g = groups.setdefault(key, {"classes": 0, "reservations": 0, "cupos": 0, "full": 0,
                                         "high": 0, "low": 0})
            g["classes"] += 1
            g["reservations"] += confirmed
            g["cupos"] += cupos
            # Clase llena = sin cupos remanentes (confirmadas cubren el cupo).
            if cupos > 0 and confirmed >= cupos:
                g["full"] += 1
            # Recurrencia de ocupación alta (>= 0.8) / baja (<= 0.5) por clase.
            ratio = confirmed / cupos if cupos else 0
            if ratio >= HIGH_OCCUPANCY_THRESHOLD:
                g["high"] += 1
            if ratio <= LOW_OCCUPANCY_THRESHOLD:
                g["low"] += 1

        result = []
        for key, g in groups.items():
            studio_k, room_id, room_name, act_id, act_name, weekday, start_time = key
            occupancy_pct = round(g["reservations"] / g["cupos"] * 100, 2) if g["cupos"] else 0
            full_classes_pct = round(g["full"] / g["classes"] * 100, 2) if g["classes"] else 0
            result.append({
                "studio_id": studio_k,
                "room_id": room_id,
                "room_name": room_name,
                "activity_subtype_id": act_id,
                "activity_subtype_name": act_name,
                "weekday": weekday,
                "weekday_name": WEEKDAY_NAMES[weekday] if weekday is not None else None,
                "start_time": start_time.strftime('%H:%M:%S') if start_time else None,
                "classes": g["classes"],
                "total_reservations": g["reservations"],
                "total_cupos": g["cupos"],
                "occupancy_pct": occupancy_pct,
                "full_classes_pct": full_classes_pct,
                "high_occupancy_recurrence": round(g["high"] / g["classes"], 2) if g["classes"] else 0,
                "low_occupancy_recurrence": round(g["low"] / g["classes"], 2) if g["classes"] else 0,
            })
        result.sort(key=lambda r: r["occupancy_pct"], reverse=True)
        return Response(result, status=status.HTTP_200_OK)


class PlanValidityViewSet(viewsets.ViewSet):
    """Vigencia de planes.

    Clasifica los PersonActivePlan (no eliminados) por su exp_date — NO por si el
    alumno pagó en el mes calendario. Devuelve:
      - active: planes con exp_date >= hoy (vigentes por fecha),
      - expired: planes con exp_date < hoy,
      - expiring_soon: vigentes cuyo exp_date cae dentro de hoy + days_ahead,
      - sessions_exhausted: vigentes por fecha pero sin sesiones restantes.
    Solo lectura. Param: days_ahead (opcional, default 7).
    Nota: PersonActivePlan no tiene vínculo a estudio -> sin filtro por estudio.
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request, *args, **kwargs):
        raw = request.query_params.get('days_ahead', '7')
        try:
            days_ahead = int(raw)
            if days_ahead < 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'days_ahead' debe ser un entero no negativo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.now().date()
        soon_limit = today + timedelta(days=days_ahead)
        plans = PersonActivePlan.objects.filter(deleted__isnull=True)

        active_qs = plans.filter(exp_date__gte=today)
        return Response({
            "today": today.isoformat(),
            "days_ahead": days_ahead,
            "active": active_qs.count(),
            "expired": plans.filter(exp_date__lt=today).count(),
            "expiring_soon": active_qs.filter(exp_date__lte=soon_limit).count(),
            "sessions_exhausted": active_qs.filter(sessions_remaining__lte=0).count(),
        }, status=status.HTTP_200_OK)


class WaitingListStatsViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Estadísticas de lista de espera.

    Agrupa las solicitudes por horario (slot.start_time) y calcula cuántas
    terminaron en una reserva. Se deduplica por (persona, clase) para no contar
    dos veces una misma solicitud. Una solicitud se considera convertida si existe
    un Appointment de esa persona para ese slot. Usa all_objects en WaitingList
    para incluir las solicitudes ya aceptadas/cerradas (que quedan soft-deleted).
    Solo lectura. Params: start_date, end_date (YYYY-MM-DD, opcionales), studio.
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        requests_qs = WaitingList.all_objects.filter(slot__isnull=False)
        if start_date:
            requests_qs = requests_qs.filter(slot__date__gte=start_date)
        if end_date:
            requests_qs = requests_qs.filter(slot__date__lte=end_date)
        if studio_ids is not None:
            requests_qs = requests_qs.filter(slot__room__studio_id__in=studio_ids)

        # Dedup por (persona, clase): solicitudes únicas con su horario.
        unique = requests_qs.values('person_id', 'slot_id', 'slot__start_time').distinct()

        groups = {}
        for r in unique:
            start_time = r['slot__start_time']
            g = groups.setdefault(start_time, {"total": 0, "converted": 0})
            g["total"] += 1
            converted = Appointment.all_objects.filter(
                person_id=r['person_id'], slot_id=r['slot_id'],
            ).exists()
            if converted:
                g["converted"] += 1

        result = [
            {
                "start_time": start_time.strftime('%H:%M:%S') if start_time else None,
                "total_requests": g["total"],
                "converted": g["converted"],
                "conversion_rate": round(g["converted"] / g["total"] * 100, 2) if g["total"] else 0,
            }
            for start_time, g in groups.items()
        ]
        result.sort(key=lambda row: row["total_requests"], reverse=True)
        return Response(result, status=status.HTTP_200_OK)


class PaymentsBreakdownViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Pagos e ingresos con desglose por medio de pago y por concepto.

    Suma de pagos registrados en el rango (opcionalmente por estudio), con desglose
    por `method` (medio de pago) y por concepto (plans_subtype de los PaymentItem).
    Solo lectura. Params: start_date, end_date (YYYY-MM-DD, opcionales), studio.
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        try:
            start_dt = datetime.combine(datetime.strptime(start_date_str, '%Y-%m-%d').date(), datetime.min.time()) if start_date_str else None
            end_dt = datetime.combine(datetime.strptime(end_date_str, '%Y-%m-%d').date(), datetime.max.time()) if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        payments = Payment.objects.filter(deleted__isnull=True)
        items = PaymentItem.objects.filter(deleted__isnull=True, payment__deleted__isnull=True)
        if start_dt:
            payments = payments.filter(date__gte=start_dt)
            items = items.filter(payment__date__gte=start_dt)
        if end_dt:
            payments = payments.filter(date__lte=end_dt)
            items = items.filter(payment__date__lte=end_dt)
        if studio_ids is not None:
            payments = payments.filter(studio_id__in=studio_ids)
            items = items.filter(payment__studio_id__in=studio_ids)

        total_income = float(payments.aggregate(total=Sum('amount'))['total'] or 0)

        by_method = [
            {"method": row['method'], "total": float(row['total'] or 0)}
            for row in payments.values('method').annotate(
                total=Sum('amount')
            ).order_by('-total')
        ]
        by_concept = [
            {"plans_subtype": row['plans_subtype__name'], "total": float(row['total'] or 0)}
            for row in items.values('plans_subtype__name').annotate(
                total=Sum('final_amount')
            ).order_by('-total')
        ]

        return Response({
            "total_income": total_income,
            "by_method": by_method,
            "by_concept": by_concept,
        }, status=status.HTTP_200_OK)


class ClassesAndReservationsViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Clases programadas y reservas por estado.

    Cuenta las clases (Slot) del período y las reservas (Appointment) diferenciando
    activas (vivas) de canceladas (soft-deleted), para no duplicar. Incluye un
    desglose por actividad. Solo lectura.
    Params: start_date, end_date (YYYY-MM-DD, opcionales), studio.
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)

        studio_ids, err = _parse_studio(request)
        if err:
            return err

        slots = Slot.objects.filter(date__isnull=False)
        appts = Appointment.all_objects.filter(slot__date__isnull=False)
        if start_date:
            slots = slots.filter(date__gte=start_date)
            appts = appts.filter(slot__date__gte=start_date)
        if end_date:
            slots = slots.filter(date__lte=end_date)
            appts = appts.filter(slot__date__lte=end_date)
        if studio_ids is not None:
            slots = slots.filter(room__studio_id__in=studio_ids)
            appts = appts.filter(slot__room__studio_id__in=studio_ids)

        total_classes = slots.count()
        reservations_active = appts.filter(deleted__isnull=True).count()
        reservations_cancelled = appts.filter(deleted__isnull=False).count()

        by_activity = [
            {
                "activity_subtype_id": row['activity_subtype'],
                "activity_subtype_name": row['activity_subtype__name'],
                "classes": row['classes'],
            }
            for row in slots.values('activity_subtype', 'activity_subtype__name').annotate(
                classes=Count('id')
            ).order_by('-classes')
        ]

        by_room = [
            {
                "room_id": row['room'],
                "room_name": row['room__name'],
                "classes": row['classes'],
            }
            for row in slots.values('room', 'room__name').annotate(
                classes=Count('id')
            ).order_by('-classes', 'room')
        ]

        return Response({
            "total_classes": total_classes,
            "reservations_active": reservations_active,
            "reservations_cancelled": reservations_cancelled,
            "by_activity": by_activity,
            "by_room": by_room,
        }, status=status.HTTP_200_OK)


class PlanUsageViewSet(viewsets.ViewSet):
    """Uso de planes: sesiones consumidas vs sin utilizar.

    Sobre los PersonActivePlan (no eliminados): sesiones totales, consumidas
    (total − remanentes) y remanentes. `unused_at_expiry` = sesiones que quedaron
    sin usar en planes ya vencidos (exp_date < hoy). Filtro opcional activity.
    Nota: 'consumido' es descuento del plan (reserva), NO asistencia efectiva — el
    modelo no registra asistencia. Solo lectura.
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        activity_raw = request.query_params.get('activity')
        try:
            activity_id = int(activity_raw) if activity_raw else None
        except (TypeError, ValueError):
            return Response({"detail": "El parámetro 'activity' debe ser un id numérico."},
                            status=status.HTTP_400_BAD_REQUEST)

        plans = PersonActivePlan.objects.filter(deleted__isnull=True)
        if activity_id is not None:
            plans = plans.filter(plans_subtype__activity_subtype_id=activity_id)

        agg = plans.aggregate(total=Sum('sessions_total'), remaining=Sum('sessions_remaining'))
        total = agg['total'] or 0
        remaining = agg['remaining'] or 0
        today = timezone.now().date()
        unused_at_expiry = plans.filter(exp_date__lt=today).aggregate(
            u=Sum('sessions_remaining'))['u'] or 0

        return Response({
            "total_sessions": total,
            "consumed_sessions": total - remaining,
            "remaining_sessions": remaining,
            "unused_at_expiry": unused_at_expiry,
            "note": "consumed_sessions = descuento del plan al reservar, no asistencia efectiva",
        }, status=status.HTTP_200_OK)


class OccupancyRateViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Ocupación y cupos del período (total).

    Para el total del período: Σ reservas confirmadas ÷ Σ cupos × 100 (cupos =
    availability remanente + confirmadas). Incluye clases llenas. Solo lectura.
    Params: start_date, end_date (YYYY-MM-DD, opcionales), studio.
    Nota: usa el estado actual reconstruido, no un snapshot histórico al inicio
    de la clase (eso requiere conservar historial; ver nota de la card).
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)
        studio_ids, err = _parse_studio(request)
        if err:
            return err

        slots = Slot.objects.filter(date__isnull=False)
        if start_date:
            slots = slots.filter(date__gte=start_date)
        if end_date:
            slots = slots.filter(date__lte=end_date)
        if studio_ids is not None:
            slots = slots.filter(room__studio_id__in=studio_ids)
        slots = slots.annotate(
            confirmed=Count('appointments', filter=Q(appointments__deleted__isnull=True))
        )

        total_classes = 0
        total_reservations = 0
        total_cupos = 0
        full_classes = 0
        for s in slots:
            confirmed = s.confirmed or 0
            cupos = (s.availability or 0) + confirmed
            total_classes += 1
            total_reservations += confirmed
            total_cupos += cupos
            if cupos > 0 and confirmed >= cupos:
                full_classes += 1

        occupancy_pct = round(total_reservations / total_cupos * 100, 2) if total_cupos else 0
        full_classes_pct = round(full_classes / total_classes * 100, 2) if total_classes else 0
        return Response({
            "total_classes": total_classes,
            "total_reservations": total_reservations,
            "total_cupos": total_cupos,
            "occupancy_pct": occupancy_pct,
            "full_classes": full_classes,
            "full_classes_pct": full_classes_pct,
        }, status=status.HTTP_200_OK)


class OccupancyEvolutionViewSet(StudioNoticeMixin, viewsets.ViewSet):
    """Evolución de la ocupación por período y franja.

    Agrupa por (período, franja) con franja = (estudio, sala, actividad, día de
    la semana, hora), para comparar franjas equivalentes período a período.
    Ocupación = Σ reservas ÷ Σ cupos. Solo cuenta clases reales (slots
    existentes): los feriados sin clase no se cuentan como clases vacías.
    Ordenado por franja y período (cada franja queda contigua). Solo lectura.
    Params: granularity (month|week, default month; week = año-semana ISO
    p.ej. 2026-W24), start_date, end_date (YYYY-MM-DD, opcionales), studio.
    """
    permission_classes = [IsAdministrador | IsSuper]

    def list(self, request, *args, **kwargs):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usar YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)
        granularity = request.query_params.get('granularity', 'month')
        if granularity not in ('month', 'week'):
            return Response({"detail": "El parámetro 'granularity' debe ser 'month' o 'week'."},
                            status=status.HTTP_400_BAD_REQUEST)
        studio_ids, err = _parse_studio(request)
        if err:
            return err

        slots = Slot.objects.filter(date__isnull=False, start_time__isnull=False).select_related('room')
        if start_date:
            slots = slots.filter(date__gte=start_date)
        if end_date:
            slots = slots.filter(date__lte=end_date)
        if studio_ids is not None:
            slots = slots.filter(room__studio_id__in=studio_ids)
        slots = slots.annotate(
            confirmed=Count('appointments', filter=Q(appointments__deleted__isnull=True))
        )

        groups = {}
        for s in slots:
            confirmed = s.confirmed or 0
            cupos = (s.availability or 0) + confirmed
            if granularity == 'week':
                iso = s.date.isocalendar()
                period = f"{iso[0]}-W{iso[1]:02d}"
            else:
                period = s.date.strftime('%Y-%m')
            key = (
                s.room.studio_id if s.room else None,
                s.room_id, s.activity_subtype_id,
                s.date.weekday(), s.start_time, period,
            )
            g = groups.setdefault(key, {"reservations": 0, "cupos": 0, "classes": 0})
            g["reservations"] += confirmed
            g["cupos"] += cupos
            g["classes"] += 1

        def _sort_key(k):
            studio_k, room_id, act_id, weekday, start_time, period = k
            return (studio_k or 0, room_id or 0, act_id or 0, weekday, start_time, period)

        evolution = []
        for key in sorted(groups, key=_sort_key):
            studio_k, room_id, act_id, weekday, start_time, period = key
            g = groups[key]
            evolution.append({
                "period": period,
                "studio_id": studio_k,
                "room_id": room_id,
                "activity_subtype_id": act_id,
                "weekday": weekday,
                "weekday_name": WEEKDAY_NAMES[weekday],
                "start_time": start_time.strftime('%H:%M:%S'),
                "classes": g["classes"],
                "total_reservations": g["reservations"],
                "total_cupos": g["cupos"],
                "occupancy_pct": round(g["reservations"] / g["cupos"] * 100, 2) if g["cupos"] else 0,
            })
        return Response(evolution, status=status.HTTP_200_OK)


class TenureViewSet(viewsets.ViewSet):
    """Permanencia de los alumnos activos.

    Antigüedad desde el inicio del período activo (Person.created_at), agrupada por
    rangos. Solo lectura.
    Nota: usa created_at como inicio; el sistema no guarda historial de
    altas/bajas/reactivaciones, así que una reactivación no reinicia la antigüedad.
    """
    permission_classes = [IsAdministrador | IsSuper]

    RANGES = ['<1m', '1-3m', '3-6m', '6-12m', '>12m']

    @staticmethod
    def _bucket(days):
        if days < 30:
            return '<1m'
        if days < 90:
            return '1-3m'
        if days < 180:
            return '3-6m'
        if days < 365:
            return '6-12m'
        return '>12m'

    def list(self, request, *args, **kwargs):
        today = timezone.now().date()
        people = Person.all_objects.filter(deleted__isnull=True, created_at__isnull=False)

        ranges = {r: 0 for r in self.RANGES}
        total = 0
        days_sum = 0
        for created_at in people.values_list('created_at', flat=True):
            days = (today - created_at.date()).days
            if days < 0:
                days = 0
            ranges[self._bucket(days)] += 1
            days_sum += days
            total += 1

        average_days = round(days_sum / total, 1) if total else None
        return Response({
            "total": total,
            "average_days": average_days,
            "ranges": ranges,
        }, status=status.HTTP_200_OK)
