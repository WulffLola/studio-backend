from rest_framework import viewsets, status
from django.conf import settings
from rest_framework.response import Response
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from .models import Payment
from apps.payment_method.models import PaymentMethod
from apps.users.models import CustomUser 
from apps.people.models import Person, PersonActivePlan
from apps.people.serializer import PersonActivePlanSerializer
import requests
from apps.expenses.serializer import ExpenseSerializer
from apps.expenses.models import Expense
from apps.actions.models import Action 
from .serializer import PaymentSerializer, PaymentItemSerializer
from .services import (
    apply_combo_discounts,
    check_plans_availability,
    build_payment_items,
    register_active_plans,
)
from .models import PaymentItem
from django.db import transaction
from django.db.models import Prefetch
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.core.files import File
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import os
from collections import defaultdict
from decimal import Decimal
from django.utils import timezone
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper
from apps.studios.filters import StudioFilterMixin, resolve_studios, deleted_studios_detail
import logging

logger = logging.getLogger(__name__)


def build_receipt_content(person, formatted_payment_date, enriched, names, next_exp):
    """Arma el contenido del comprobante de pago como lista ordenada de
    (estilo, texto); estilos: 'title' | 'subtitle' | 'normal'. Función pura (sin
    reportlab) para poder testear el contenido.

    - Encabezado: "DENISE SOULES STUDIO".
    - Cada plan: solo nombre y monto (sin vencimiento individual).
    - Si hay `next_exp`: próximo vencimiento general + aviso de baja automática a
      los 7 días, con la fecha del vencimiento en dd-mm-aaaa. Si no hay, se omiten.
    """
    cents = Decimal('0.01')
    content = [
        ('title', "Comprobante de Pago"),
        ('subtitle', "DENISE SOULES STUDIO"),
        ('normal',
         f"Se deja constancia de que <b>{person.name} {person.last_name}</b> "
         f"ha realizado el pago correspondiente el día {formatted_payment_date}:"),
    ]
    total = Decimal('0')
    for it in enriched:
        sid = it['plans_subtype_id']
        name = names.get(sid, f"Plan {sid}")
        amount = it['final_amount'].quantize(cents)
        total += amount
        content.append(('normal', f"&bull; <b>{name}</b> — ${amount}"))
    content.append(('normal', f"<b>Total: ${total}</b>"))
    if next_exp:
        exp_txt = next_exp.strftime('%d-%m-%Y')
        content.append(('normal',
            f"Recuerde que su próximo vencimiento es el <b>{exp_txt}</b>. "
            "Tres días antes se le enviará un recordatorio."))
        content.append(('normal',
            "Si no realiza el pago dentro de los 7 días posteriores a la fecha de "
            f"vencimiento ({exp_txt}), su suscripción será dada de baja automáticamente."))
    return content


class PaymentViewSet(StudioFilterMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [ IsAdministrador | IsConsultor | IsSuper]
    studio_lookup = 'studio'

    def get_queryset(self):
        qs = Payment.all_objects.for_user(self.request.user).select_related('person').prefetch_related(
            'person__sworn_statements__statement',
            Prefetch(
                'items__plans_subtype__payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )
        # filtro opcional ?studio=<id>[,<id>...] (ver apps/studios/filters.py)
        return self.filter_by_studio(qs)

    def verify_code(self, code, request):
        """
        Verifica la validez del código y maneja el caso de 'admin' o 'super'.
        """
        if not code:
            return Response({"detail": "El campo 'code' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        # Verificar si el código es "admin" o "super" y usar el usuario logueado
        if code == "admin" or code == "super":
            if request.user.is_authenticated:
                return request.user
            else:
                return Response({"detail": "No hay ningún usuario logueado."}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar el usuario que tenga ese código
        try:
            user = CustomUser.objects.get(code=code)
            return user
        except CustomUser.DoesNotExist:
            return Response({"detail": "El código proporcionado no corresponde a ningún usuario."}, status=status.HTTP_400_BAD_REQUEST)
        
    
    def generate_pdf_multi(self, payment, person, active_plans, enriched):
        """
        Comprobante para pagos multi-plan: una línea por plan (nombre y monto
        final), total, próximo vencimiento general y aviso de baja a los 7 días
        (ver build_receipt_content). Guarda el PDF en payment.pdf_file y devuelve
        el path. Lanza ValueError si falla.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        dni = person.dni
        formatted_payment_date = payment.date.strftime("%d-%m-%Y")
        pdf_filename = f"CP_{today}_{dni}.pdf"
        pdf_folder = os.path.join(settings.MEDIA_ROOT, 'payments')
        if not os.path.exists(pdf_folder):
            os.makedirs(pdf_folder)
        pdf_path = os.path.join(pdf_folder, pdf_filename)

        next_exp = min((ap.exp_date for ap in active_plans), default=None)

        from apps.plans_subtype.models import PlansSubtype
        names = {
            ps.id: ps.name
            for ps in PlansSubtype.objects.filter(
                pk__in=[it['plans_subtype_id'] for it in enriched]
            )
        }

        try:
            pdf = canvas.Canvas(pdf_path, pagesize=letter)
            pdf.setTitle(f"Comprobante de Pago - {person.name} {person.last_name} - {today}")

            doc = SimpleDocTemplate(pdf_path, pagesize=letter)
            title_style = ParagraphStyle('TitleStyle', fontName='Helvetica-Bold', fontSize=16, spaceAfter=30, alignment=1)
            subtitle_style = ParagraphStyle('SubtitleStyle', fontName='Helvetica-Bold', fontSize=14, spaceAfter=20, alignment=1)
            normal_style = ParagraphStyle('NormalStyle', fontSize=12, leading=18, spaceAfter=12)

            styles = {'title': title_style, 'subtitle': subtitle_style, 'normal': normal_style}
            content = build_receipt_content(person, formatted_payment_date, enriched, names, next_exp)
            elements = [Paragraph(text, styles[kind]) for kind, text in content]
            elements.append(Spacer(1, 12))

            doc.build(elements)

            with open(pdf_path, 'rb') as f:
                payment.pdf_file.save(pdf_filename, File(f), save=True)

            return pdf_path
        except Exception as e:
            raise ValueError(f"Error al generar el PDF: {str(e)}")

    def send_pdf(self, pdf_path, person, message):
        url = os.getenv("API_WPP_SEND_PDF")
        phone_number = person.phone
        if not phone_number:
            raise ValueError("El usuario no tiene un número de teléfono registrado.")

        payload = {"number": phone_number, "message": message}
        files = {"pdf": open(pdf_path, "rb")}

        try:
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
        except requests.RequestException as e:
            raise ValueError(f"Error al enviar el PDF: {e}")
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        
    # Acción personalizada para descargar el PDF
    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        payment = self.get_object()  # Obtener el pago específico basado en el ID
        
        if not payment.pdf_file:
            return Response({"detail": "El archivo PDF no existe."}, status=status.HTTP_404_NOT_FOUND)
        
        # Ruta al archivo PDF en el sistema
        pdf_path = payment.pdf_file.path
        if os.path.exists(pdf_path):
            response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(pdf_path)}"'
            return response
        else:
            return Response({"detail": "El archivo PDF no se encontró."}, status=status.HTTP_404_NOT_FOUND)

    def _create_with_items(self, request, serializer, user, person, payment_date, items_data):
        """
        Crea un pago con uno o más PaymentItem (cada uno asociado a un
        plans_subtype), aplica descuentos combo, calcula el total y crea/renueva
        los planes activos del alumno. Genera el comprobante PDF (ver
        generate_pdf_multi) e intenta enviarlo por WhatsApp.
        """
        from apps.payments.services import normalize_and_validate_items
        norm_items, error = normalize_and_validate_items(items_data)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        method = request.data.get('method')
        observation = request.data.get('observation')

        try:
            enriched, applied_combos, total = build_payment_items(norm_items)

            with transaction.atomic():
                payment = serializer.save(
                    user=user,
                    date=payment_date,
                    amount=total,
                    method=method,
                    observation=observation,
                )
                for it in enriched:
                    PaymentItem.objects.create(
                        payment=payment,
                        person=person,
                        plans_subtype_id=it['plans_subtype_id'],
                        base_amount=Decimal(str(it['base_amount'])),
                        discount_pct=it['discount_pct'],
                        discount_source=it.get('discount_source', 'none'),
                    )
                active_plans = register_active_plans(person, enriched, payment_date)
        except Exception as e:
            return Response(
                {"code": "error", "message": f"Error al crear el pago: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Registrar la acción.
        new_value = [
            {'field': 'Alumno', 'value': f"{person.name} {person.last_name}"},
            {'field': 'Total', 'value': str(total)},
            {'field': 'Método', 'value': method},
            {'field': 'Planes', 'value': len(enriched)},
        ]
        Action.objects.create(
            user=user,
            action="Crear",
            target="Pago",
            target_id=payment.id,
            new_value=new_value,
        )

        # Todo pago genera comprobante PDF; se intenta enviar por WhatsApp con
        # la misma degradación elegante del flujo legacy (el pago ya quedó
        # registrado, así que un fallo del PDF/WhatsApp no lo revierte).
        warning = None
        try:
            pdf_path = self.generate_pdf_multi(payment, person, active_plans, enriched)
            try:
                message = f"Gracias {person.name}, se registró su pago 🥰❣️"
                self.send_pdf(pdf_path, person, message)
            except requests.RequestException as e:
                warning = f"El pago se registró, pero hubo un error al enviar el mensaje por WhatsApp: {str(e)}"
            except ValueError as e:
                if "El usuario no tiene un número de teléfono registrado" in str(e):
                    warning = ("El pago se registró, pero no se pudo enviar el mensaje por WhatsApp "
                               "porque el usuario no tiene un número de teléfono registrado.")
                else:
                    warning = f"El pago se registró, pero hubo un error al enviar el mensaje por WhatsApp: {str(e)}"
        except ValueError as e:
            warning = f"El pago se registró, pero hubo un error al generar el PDF: {str(e)}"

        pdf_url = request.build_absolute_uri(f'/payments/download/{payment.id}/')
        out = self.get_serializer(payment)
        body = {
            'payment': out.data,
            'total': str(total),
            'applied_combos': applied_combos,
            'active_plans': [
                {
                    'plans_subtype': ap.plans_subtype_id,
                    'exp_date': ap.exp_date,
                    'sessions_remaining': ap.sessions_remaining,
                }
                for ap in active_plans
            ],
            'pdf_download_url': pdf_url,
        }
        if warning:
            body['warning'] = warning
        return Response(body, status=status.HTTP_201_CREATED)

    def _update_with_items(self, request, payment, serializer, user, person, payment_date, items_data):
        """
        Edita un pago multi-plan: reconstruye sus PaymentItem (reemplazo),
        recalcula total/combos y regenera el PDF. NO toca PersonActivePlan.
        """
        from apps.payments.services import normalize_and_validate_items
        from apps.people.models import PersonActivePlan

        norm_items, error = normalize_and_validate_items(items_data)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        method = request.data.get('method', payment.method)
        observation = request.data.get('observation', payment.observation)

        old_value = [
            {'field': 'Alumno', 'value': f"{person.name} {person.last_name}"},
            {'field': 'Monto', 'value': str(payment.amount)},
            {'field': 'Método', 'value': payment.method},
            {'field': 'Planes', 'value': payment.items.count()},
        ]

        try:
            enriched, applied_combos, total = build_payment_items(norm_items)
            with transaction.atomic():
                PaymentItem.objects.filter(payment=payment).delete()  # reemplazo
                payment.amount = total
                payment.method = method
                payment.observation = observation
                if serializer.validated_data.get('date'):
                    payment.date = payment_date
                payment.save()
                for it in enriched:
                    PaymentItem.objects.create(
                        payment=payment,
                        person=person,
                        plans_subtype_id=it['plans_subtype_id'],
                        base_amount=Decimal(str(it['base_amount'])),
                        discount_pct=it['discount_pct'],
                        discount_source=it.get('discount_source', 'none'),
                    )
        except Exception as e:
            return Response(
                {"code": "error", "message": f"Error al editar el pago: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        Action.objects.create(
            user=user, action="Actualizar", target="Pago", target_id=payment.id,
            old_value=old_value,
            new_value=[
                {'field': 'Total', 'value': str(total)},
                {'field': 'Método', 'value': method},
                {'field': 'Planes', 'value': len(enriched)},
            ],
        )

        # PDF (degradación elegante). NO se modifican los planes activos: se leen
        # los vigentes del alumno para esos subtypes solo para el comprobante.
        warning = None
        active_plans = list(
            PersonActivePlan.objects.filter(
                person=person,
                plans_subtype_id__in=[it['plans_subtype_id'] for it in enriched],
            )
        )
        try:
            pdf_path = self.generate_pdf_multi(payment, person, active_plans, enriched)
            try:
                message = f"Hola {person.name}, su pago fue actualizado. Aquí está el nuevo comprobante. 😊"
                self.send_pdf(pdf_path, person, message)
            except requests.RequestException as e:
                warning = f"El pago se editó, pero hubo un error al enviar el mensaje por WhatsApp: {str(e)}"
            except ValueError as e:
                if "El usuario no tiene un número de teléfono registrado" in str(e):
                    warning = ("El pago se editó, pero no se pudo enviar el mensaje por WhatsApp "
                               "porque el usuario no tiene un número de teléfono registrado.")
                else:
                    warning = f"El pago se editó, pero hubo un error al enviar el mensaje por WhatsApp: {str(e)}"
        except ValueError as e:
            warning = f"El pago se editó, pero hubo un error al generar el PDF: {str(e)}"

        pdf_url = request.build_absolute_uri(f'/payments/download/{payment.id}/')
        out = self.get_serializer(payment)
        body = {
            'payment': out.data,
            'total': str(total),
            'applied_combos': applied_combos,
            'pdf_download_url': pdf_url,
        }
        if warning:
            body['warning'] = warning
        return Response(body, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        code = request.data.get('code')
        user = self.verify_code(code, request)
        if isinstance(user, Response):
            return user

        items_data = request.data.get('items')
        if not items_data:
            return Response(
                {"detail": "El campo 'items' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar clases disponibles antes de cobrar (deriva IDs desde items).
        plans_subtype_ids = request.data.get('plans_subtype_ids') or [
            it.get('plans_subtype_id')
            for it in items_data
            if isinstance(it, dict) and it.get('plans_subtype_id') is not None
        ]
        if plans_subtype_ids:
            unavailable = check_plans_availability(plans_subtype_ids)
            if unavailable:
                return Response(
                    {
                        'detail': 'No hay clases disponibles para los siguientes planes.',
                        'planes_sin_clases': unavailable,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        person = serializer.validated_data['person']
        payment_date = serializer.validated_data.get('date', datetime.now())

        return self._create_with_items(
            request, serializer, user, person, payment_date, items_data
        )

    def update(self, request, *args, **kwargs):
        payment = self.get_object()

        code = request.data.get('code')
        user = self.verify_code(code, request)
        if isinstance(user, Response):
            return user

        serializer = self.get_serializer(payment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payment_date = serializer.validated_data.get('date', datetime.now())
        person = payment.person

        items_data = request.data.get('items')
        if not items_data:
            return Response(
                {"detail": "El campo 'items' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plans_subtype_ids = request.data.get('plans_subtype_ids') or [
            it.get('plans_subtype_id')
            for it in items_data
            if isinstance(it, dict) and it.get('plans_subtype_id') is not None
        ]

        def _as_int(pid):
            try:
                return int(pid)
            except (TypeError, ValueError):
                return pid

        original_ids = {
            _as_int(pid)
            for pid in payment.items.values_list('plans_subtype_id', flat=True)
        }
        nuevos_ids = [pid for pid in plans_subtype_ids if _as_int(pid) not in original_ids]
        if nuevos_ids:
            unavailable = check_plans_availability(nuevos_ids)
            if unavailable:
                return Response(
                    {'detail': 'No hay clases disponibles para los siguientes planes.',
                     'planes_sin_clases': unavailable},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return self._update_with_items(
            request, payment, serializer, user, person, payment_date, items_data
        )

    def destroy(self, request, *args, **kwargs):
        payment = self.get_object()

        code = request.data.get('code')
        user = self.verify_code(code, request)
        if isinstance(user, Response):
            return user

        person = payment.person
        old_value = [
            {'field': 'Alumno', 'value': f"{person.name} {person.last_name}"},
            {'field': 'Monto', 'value': str(payment.amount)},
            {'field': 'Método', 'value': payment.method},
        ]

        Action.objects.create(
            user=user,
            action="Eliminar",
            target="Pago",
            target_id=payment.id,
            old_value=old_value,
        )

        payment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class PaymentsTodayViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [ IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        today = timezone.localdate()
        return Payment.objects.filter(date__date=today)


class PaymentsByDateRangeViewSet(viewsets.ViewSet):
    
    permission_classes = [ IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # Extract start_date and end_date from the request query parameters
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)

        # Check if both dates are provided
        if not start_date or not end_date:
            return Response(
                {"detail": "Both 'start_date' and 'end_date' are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate date formats
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if start_date is before end_date
        if start_date > end_date:
            return Response(
                {"detail": "'start_date' must be before 'end_date'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())


        # Filter payments within the date range
        payments = Payment.objects.filter(date__gte=start_datetime, date__lte=end_datetime)

        # Check if there are no payments in the range
        if not payments.exists():
            return Response(
                {"detail": "No payments found in the specified date range."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serialize the filtered payments
        serializer = PaymentSerializer(payments, many=True)

        # Return the serialized data
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class PaymentsLastMonthAndHalfViewSet(viewsets.ViewSet):
    permission_classes = [IsConsultor | IsAdministrador | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # "Hoy" en hora local y bounds aware: bajo USE_TZ, datetime.now() es naive y
        # en hora del server, lo que corría la ventana ±1 día cerca de medianoche.
        end_date = timezone.localdate()
        start_date = end_date - relativedelta(months=2)

        start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        payments = Payment.objects.filter(date__gte=start_datetime, date__lte=end_datetime)

        if not payments.exists():
            return Response(
                {"detail": "No payments found in the last 2 months."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serialize the filtered payments
        serializer = PaymentSerializer(payments, many=True)

        # Return the serialized data
        return Response(serializer.data, status=status.HTTP_200_OK)



class CashJournalViewSet(viewsets.ViewSet):
    
    
    permission_classes = [ IsAdministrador | IsSuper]
    
    """
    Vista para obtener todos los pagos y gastos dentro de un rango de fechas
    y calcular totales por tipo de pago y por día.
    """
    def list(self, request, *args, **kwargs):
        # Obtener start_date y end_date de los parámetros de la solicitud
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)

        # Verificar que ambas fechas estén presentes
        if not start_date or not end_date:
            return Response(
                {"detail": "Se requieren las fechas 'start_date' y 'end_date'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar el formato de las fechas y hacerlas "timezone aware"
        try:
            start_date = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end_date = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d'))
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que start_date sea menor o igual a end_date
        if start_date > end_date:
            return Response(
                {"detail": "'start_date' debe ser anterior o igual a 'end_date'."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())


        # filtro opcional ?studio=<id>[,<id>...] (400/404 en apps/studios/filters.py).
        studios = resolve_studios(request)

        # Filtrar pagos y gastos por el rango de fechas (ambos extremos inclusivos)
        payments = Payment.objects.filter(date__gte=start_datetime, date__lte=end_datetime, deleted__isnull=True)
        expenses = Expense.objects.filter(date__gte=start_datetime, date__lte=end_datetime, deleted__isnull=True)

        # El filtro por estudio se aplica ANTES de calcular los totales.
        if studios is not None:
            studio_ids = [s.pk for s in studios]
            payments = payments.filter(studio_id__in=studio_ids)
            expenses = expenses.filter(studio_id__in=studio_ids)
        elif not payments.exists() and not expenses.exists():
            # Caja global sin movimientos: mismo 404 que antes. Con ?studio, un
            # estudio sin movimientos no es error: 200 con totales en 0.
            return Response(
                {"detail": "No se encontraron pagos ni gastos en el rango de fechas especificado."},
                status=status.HTTP_404_NOT_FOUND
            )

        payments = list(payments.select_related('person').prefetch_related(
            'person__sworn_statements__statement',
            Prefetch(
                'items__plans_subtype__payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            ),
        ))
        expenses = list(expenses.select_related('type'))

        # Serializar los datos
        payment_serializer = PaymentSerializer(payments, many=True)
        expense_serializer = ExpenseSerializer(expenses, many=True)

        # Inicializar variables para los totales
        total_ingresos = Decimal(0)
        total_gastos = Decimal(0)
        total_ing_efectivo = Decimal(0)
        total_gastos_efectivo = Decimal(0)
        total_ing_transferencia = Decimal(0)
        total_gastos_transferencia = Decimal(0)

        # Inicializar variables para los totales por día
        daily_totals = defaultdict(lambda: {
            "total_gastos": Decimal(0),
            "total_ingresos": Decimal(0),
            "gastos_efectivo": Decimal(0),
            "ingresos_efectivo": Decimal(0),
            "gastos_transferencia": Decimal(0),
            "ingresos_transferencia": Decimal(0)
        })

        # Calcular los totales de ingresos
        for payment in payments:
            amount = payment.amount or Decimal('0')
            total_ingresos += amount
            if payment.method.lower() == 'efectivo':
                total_ing_efectivo += amount
                daily_totals[payment.date.date()]["ingresos_efectivo"] += amount
            elif payment.method.lower() == 'transferencia':
                total_ing_transferencia += amount
                daily_totals[payment.date.date()]["ingresos_transferencia"] += amount

            # Total ingresos por día
            daily_totals[payment.date.date()]["total_ingresos"] += amount

        # Calcular los totales de gastos
        for expense in expenses:
            amount = expense.amount or Decimal('0')
            total_gastos += amount
            if expense.method.lower() == 'efectivo':
                total_gastos_efectivo += amount
                daily_totals[expense.date.date()]["gastos_efectivo"] += amount
            elif expense.method.lower() == 'transferencia':
                total_gastos_transferencia += amount
                daily_totals[expense.date.date()]["gastos_transferencia"] += amount

            # Total gastos por día
            daily_totals[expense.date.date()]["total_gastos"] += amount

        # Calcular las diferencias
        caja_total = total_ingresos - total_gastos
        dif_efectivo = total_ing_efectivo - total_gastos_efectivo
        dif_transferencia = total_ing_transferencia - total_gastos_transferencia

        # Crear el JSON de respuesta
        response_data = {
            "caja_total": float(caja_total),
            "total_gastos_transferencia": float(total_gastos_transferencia),
            "total_ingresos_transferencia": float(total_ing_transferencia),
            "diferencia_transferencia": float(dif_transferencia),
            "total_gastos_efectivo": float(total_gastos_efectivo),
            "total_ingresos_efectivo": float(total_ing_efectivo),
            "diferencia_efectivo": float(dif_efectivo),
            "payments": payment_serializer.data,
            "expenses": expense_serializer.data,
            "detalles_por_dia": [],
            # estudios filtrados (lista de ids) o null si es global.
            "studio": [s.pk for s in studios] if studios is not None else None,
        }
        detail = deleted_studios_detail(studios)
        if detail:
            response_data["detail"] = detail

        # Agregar los detalles por día
        for date, totals in sorted(daily_totals.items()):
            response_data["detalles_por_dia"].append({
                "fecha": date,
                "total_gastos": float(totals["total_gastos"]),
                "total_ingresos": float(totals["total_ingresos"]),
                "gastos_efectivo": float(totals["gastos_efectivo"]),
                "ingresos_efectivo": float(totals["ingresos_efectivo"]),
                "gastos_transferencia": float(totals["gastos_transferencia"]),
                "ingresos_transferencia": float(totals["ingresos_transferencia"]),
                "diferencia_dia": float(totals["total_ingresos"] - totals["total_gastos"])
            })

        return Response(response_data, status=status.HTTP_200_OK)


    
class CashJournalTodayViewSet(viewsets.ViewSet):
    """
    Vista para obtener todos los pagos y gastos de hoy, ordenados por hora.
    """
    
    permission_classes = [ IsAdministrador | IsConsultor | IsSuper]
    
    def list(self, request, *args, **kwargs):
        # filtro opcional ?studio=<id>[,<id>...] (400/404 en apps/studios/filters.py).
        studios = resolve_studios(request)

        # Obtener la fecha actual (misma lógica de "hoy" que antes, sin cambios)
        today = timezone.localdate()

        # Filtrar pagos y gastos por la fecha de hoy
        payments = Payment.objects.filter(date__date=today, deleted__isnull=True).order_by('date')
        expenses = Expense.objects.filter(date__date=today, deleted__isnull=True).order_by('date')

        # El filtro por estudio se aplica sobre los querysets, ANTES de calcular
        # cualquier total: movimientos y totales salen del mismo conjunto.
        if studios is not None:
            studio_ids = [s.pk for s in studios]
            payments = payments.filter(studio_id__in=studio_ids)
            expenses = expenses.filter(studio_id__in=studio_ids)
        elif not payments.exists() and not expenses.exists():
            # Caja global sin movimientos: mismo 404 que antes. Con ?studio, un
            # estudio sin movimientos NO es error: 200 con listas vacías y totales en 0.
            return Response(
                {"detail": "No se encontraron pagos ni gastos para hoy."},
                status=status.HTTP_404_NOT_FOUND
            )

        payments = list(payments.select_related('person').prefetch_related(
            'person__sworn_statements__statement',
            Prefetch(
                'items__plans_subtype__payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            ),
        ))
        expenses = list(expenses.select_related('type'))

        # Serializar los datos
        payment_serializer = PaymentSerializer(payments, many=True)
        expense_serializer = ExpenseSerializer(expenses, many=True)

        ingresos = _cash_totals(payments)
        gastos = _cash_totals(expenses)

        # Retornar los pagos y gastos en la misma respuesta (campos existentes
        # sin cambios; se agregan "studio" y los totales).
        body = {
            "payments": payment_serializer.data,
            "expenses": expense_serializer.data,
            "studio": [s.pk for s in studios] if studios is not None else None,
            "caja_total": float(ingresos["total"] - gastos["total"]),
            "total_ingresos": float(ingresos["total"]),
            "total_gastos": float(gastos["total"]),
            "total_ingresos_efectivo": float(ingresos["efectivo"]),
            "total_gastos_efectivo": float(gastos["efectivo"]),
            "diferencia_efectivo": float(ingresos["efectivo"] - gastos["efectivo"]),
            "total_ingresos_transferencia": float(ingresos["transferencia"]),
            "total_gastos_transferencia": float(gastos["transferencia"]),
            "diferencia_transferencia": float(ingresos["transferencia"] - gastos["transferencia"]),
        }
        detail = deleted_studios_detail(studios)
        if detail:
            body["detail"] = detail
        return Response(body, status=status.HTTP_200_OK)


def _cash_totals(movements):
    """Suma total / efectivo / transferencia de pagos o gastos ya filtrados
. Mismo criterio que /cash_journal/ (método sin distinguir
    mayúsculas). `amount` es CharField: un monto no numérico se cuenta como 0 y
    se loguea, para que un dato sucio no tire abajo la caja del día."""
    totals = {"total": Decimal(0), "efectivo": Decimal(0), "transferencia": Decimal(0)}
    for m in movements:
        try:
            amount = Decimal(str(m.amount).strip())
            if not amount.is_finite():
                raise ValueError
        except Exception:
            logger.warning("cash_journal_today: monto no numérico %r en %s id=%s",
                           m.amount, type(m).__name__, m.pk)
            continue
        totals["total"] += amount
        method = (m.method or '').strip().lower()
        if method in ("efectivo", "transferencia"):
            totals[method] += amount
    return totals
    

class TeacherCashJournalTodayViewSet(viewsets.ViewSet):
    
    
    permission_classes = [ IsAdministrador | IsConsultor | IsSuper]
    
    """
    Vista para obtener todos los pagos de hoy y los gastos de tipo 'Gastos Chicos', ordenados por hora.
    """
    def list(self, request, *args, **kwargs):
        # Obtener la fecha actual
        today = timezone.localdate()

        # Filtrar todos los pagos por la fecha de hoy
        payments = Payment.objects.filter(date__date=today, deleted__isnull=True).order_by('date')

        # Filtrar gastos por la fecha de hoy, pero solo los que sean del tipo 'Gastos Chicos'
        expenses = Expense.objects.filter(
            date__date=today,
            deleted__isnull=True,
            type__name__iexact="Gastos Chicos"  # Ignorar mayúsculas y minúsculas
        ).order_by('date')

        # Verificar si no hay pagos ni gastos de tipo 'Gastos Chicos'
        if not payments.exists() and not expenses.exists():
            return Response(
                {"detail": "No se encontraron pagos ni gastos de tipo 'Gastos Chicos' para hoy."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serializar los datos
        payment_serializer = PaymentSerializer(payments, many=True)
        expense_serializer = ExpenseSerializer(expenses, many=True)

        # Retornar los pagos y los gastos chicos en la respuesta
        return Response({
            "payments": payment_serializer.data,
            "expenses_chicos": expense_serializer.data
        }, status=status.HTTP_200_OK)


class PaymentItemViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentItemSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        return PaymentItem.all_objects.for_user(self.request.user)


class OverduePaymentsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /overdue-payments/
    Lista los PersonActivePlan cuyo exp_date ya venció (exp_date < hoy).
    Permite filtrar por person_id: /overdue-payments/?person_id=3
    """
    serializer_class = PersonActivePlanSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        today = timezone.now().date()
        qs = PersonActivePlan.objects.filter(
            exp_date__lt=today,
            deleted__isnull=True,
        ).select_related('person', 'plans_subtype').prefetch_related(
            Prefetch(
                'plans_subtype__payment_methods',
                queryset=PaymentMethod.objects.filter(deleted__isnull=True),
                to_attr='alive_payment_methods',
            )
        )
        person_id = self.request.query_params.get('person_id')
        if person_id:
            qs = qs.filter(person_id=person_id)
        return qs


class ComputeDiscountView(viewsets.ViewSet):
    """
    POST /compute-discount/
    Body: [{"plans_type_id": 1, "base_amount": "1000"}, ...]
    Devuelve cada ítem con discount_pct y final_amount calculados.
    """
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def create(self, request, *args, **kwargs):
        items = request.data
        if not isinstance(items, list) or not items:
            return Response(
                {"detail": "Se esperaba una lista de ítems con plans_type_id y base_amount."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            enriched_items, applied_combos = apply_combo_discounts(items)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "items": enriched_items,
            "applied_combos": applied_combos,
        }, status=status.HTTP_200_OK)