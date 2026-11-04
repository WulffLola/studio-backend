from apps.user_type.permisos import is_admin_or_super
from rest_framework import viewsets, status
from rest_framework.response import Response
from datetime import datetime
from django.utils import timezone
from .models import Expense
from .serializer import ExpenseSerializer
from apps.teachers.models import Teacher
from apps.expense_type.models import ExpenseType  # Importar el modelo de tipo de pago
from apps.actions.models import Action
from apps.teachers_hours.models import Hour
from apps.users.models import CustomUser  # Para verificar el código
from django.db.models import Sum
from django.db.models.functions import TruncDate
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper
from apps.studios.filters import StudioFilterMixin

class ExpenseViewSet(StudioFilterMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]
    studio_lookup = 'studio'

    def get_queryset(self):
        qs = Expense.all_objects.for_user(self.request.user).select_related('type')
        # filtro opcional ?studio=<id>[,<id>...] (ver apps/studios/filters.py)
        return self.filter_by_studio(qs)

    def verify_code(self, code, request):
        """
        Verifica la validez del código y maneja el caso de 'admin' o 'super'.
        """
        if not code:
            return Response({"detail": "El campo 'code' es obligatorio para 'Gastos Chicos'."}, status=status.HTTP_400_BAD_REQUEST)

        # Verificar si el código es "admin" o "super" y usar el usuario logueado
        if code == "admin":
            # El atajo sin código es solo para Administrador y Super:
            # el Consultor tiene que ingresar un código válido.
            if is_admin_or_super(request.user):
                return request.user
            if request.user.is_authenticated:
                return Response({"detail": "Tenés que ingresar un código válido."}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({"detail": "No hay ningún usuario logueado."}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar el usuario que tenga ese código
        try:
            user = CustomUser.objects.get(code=code)
            return user
        except CustomUser.DoesNotExist:
            return Response({"detail": "El código proporcionado no corresponde a ningún usuario."}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()

        # Obtener el tipo de gasto por el ID (usando type_id)
        expense_type_id = data.get('type_id')
        if not expense_type_id:
            return Response({"detail": "El campo 'type_id' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            expense_type = ExpenseType.objects.get(pk=expense_type_id)
        except ExpenseType.DoesNotExist:
            return Response({"detail": "El tipo de gasto no existe."}, status=status.HTTP_404_NOT_FOUND)

        # Si el tipo de gasto es "Sueldo", verificar que se haya pasado el campo teacher
        if "Sueldo" in expense_type.name:
            teacher_id = data.get('teacher')
            if not teacher_id:
                return Response({"detail": "El campo 'teacher' es obligatorio para el tipo de gasto 'Sueldo'."}, status=status.HTTP_400_BAD_REQUEST)

            # Obtener la profesora y actualizar su campo last_payment con la fecha actual
            try:
                teacher = Teacher.objects.get(pk=teacher_id)
            except Teacher.DoesNotExist:
                return Response({"detail": "La profesora no existe."}, status=status.HTTP_404_NOT_FOUND)

            # Actualizar el campo last_payment de la profesora
            teacher.last_payment = datetime.now().date()
            teacher.save()

            # Actualizar la observación del pago con el nombre y apellido de la profesora
            data['observation'] = f"Pago a {teacher.name} {teacher.last_name}"
            
            # Obtener el mes actual
            month = int(datetime.now().strftime('%m')) 

            # Buscar el registro de Hour correspondiente al mes y profesora
            hour = Hour.objects.filter(teacher=teacher, month=month, deleted__isnull=True).first()
            if not hour:
                return Response({"detail": "No se encontró un registro de horas para esta profesora en el mes actual."}, status=status.HTTP_400_BAD_REQUEST)

            # Verificar que el monto no exceda el campo left
            amount = float(data.get('amount', 0))
            left_value = float(hour.left or 0)
            if left_value - amount < 0:
                return Response({"detail": "El monto excede las horas disponibles para el sueldo de esa profesora."}, status=status.HTTP_400_BAD_REQUEST)

            # Restar el monto al campo left
            hour.left = str(left_value - amount)
            hour.save()

        # Si el tipo de gasto es "Gastos Chicos", requerir el código y registrar la acción
        if expense_type.name == "Gastos Chicos":
            code = data.get('code')
            user = self.verify_code(code, request)

            if isinstance(user, Response):
                return user  # Si el código es inválido, retornará un error

            # Registrar la acción
            Action.objects.create(
                user=user,
                action="Crear",
                target="Gasto",
                target_id=None,  # El ID del gasto se agregará después de la creación
                new_value=[{'field': 'Monto', 'value': data.get('amount')}, 
                           {'field': 'Tipo', 'value': expense_type.name},
                           {'field': 'Método', 'value': data.get('method')}]
            )

        # Continuar con la creación del Expense
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Actualizar la acción con el ID del gasto creado si es "Gastos Chicos"
        if expense_type.name == "Gastos Chicos":
            last_expense = Expense.objects.latest('id')
            Action.objects.filter(target="expenses", target_id=None).update(target_id=last_expense.id)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = request.data.copy()
        expense_type = instance.type

        # Si el tipo de gasto es "Gastos Chicos", requerir el código y registrar la acción
        if expense_type.name == "Gastos Chicos":
            code = data.get('code')
            user = self.verify_code(code, request)

            if isinstance(user, Response):
                return user  # Si el código es inválido, retornará un error

            # Registrar los valores antiguos
            old_value = [
                {'field': 'Monto', 'value': str(instance.amount) if instance.amount is not None else None},
                {'field': 'Tipo', 'value': expense_type.name},
                {'field': 'Método', 'value': instance.method}
            ]

        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # Si es "Gastos Chicos", registrar los valores nuevos
        if expense_type.name == "Gastos Chicos":
            new_value = [
                {'field': 'Monto', 'value': (lambda a: str(a) if a is not None else None)(serializer.validated_data.get('amount', instance.amount))},
                {'field': 'Tipo', 'value': expense_type.name},
                {'field': 'Método', 'value': serializer.validated_data.get('method', instance.method)}
            ]

            Action.objects.create(
                user=user,
                action="Actualizar",
                target="Gastos",
                target_id=instance.id,
                old_value=old_value,
                new_value=new_value
            )

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        expense_type = instance.type

        code = request.data.get('code')
        user = self.verify_code(code, request)
        if isinstance(user, Response):
            return user  # Si el código es inválido, retornará un error

        # Si el tipo de gasto es "Gastos Chicos", registrar la acción
        if expense_type.name == "Gastos Chicos":
            # Registrar los valores antiguos antes de eliminar
            old_value = [
                {'field': 'Monto', 'value': str(instance.amount) if instance.amount is not None else None},
                {'field': 'Tipo', 'value': expense_type.name},
                {'field': 'Método', 'value': instance.method}
            ]

            Action.objects.create(
                user=user,
                action="Eliminar",
                target="Gasto",
                target_id=instance.id,
                old_value=old_value,
                new_value=[{'field': 'Estado', 'value': 'Eliminado'}]
            )

        # Soft delete: actualiza el campo `deleted`
        instance.deleted = datetime.now()
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    
class TotalExpensesViewSet(viewsets.ViewSet):
    
    permission_classes = [IsAdministrador | IsSuper | IsConsultor]
    
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

        

        # Sumar todos los gastos en el rango de fechas
        expenses = Expense.objects.filter(date__gte=start_datetime, date__lte=end_datetime)
        total_expenses = float(expenses.aggregate(t=Sum('amount'))['t'] or 0)

        return Response({
            "total_expenses": total_expenses
        }, status=status.HTTP_200_OK)



class ExpensesTodayTeachersViewSet(viewsets.ViewSet):
    """
    ViewSet para mostrar todos los gastos del tipo "Gastos Chicos" del día actual (no case sensitive).
    """
    permission_classes = [IsAdministrador | IsSuper | IsConsultor]

    def list(self, request, *args, **kwargs):
        try:
            # Obtener el tipo de gasto "Gastos Chicos" sin importar mayúsculas/minúsculas
            expense_type = ExpenseType.objects.get(name__iexact="Gastos Chicos")
        except ExpenseType.DoesNotExist:
            return Response(
                {"detail": "El tipo de gasto 'Gastos Chicos' no existe."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Filtrar los gastos del tipo "Gastos Chicos" creados hoy
        today = timezone.localdate()
        expenses_today = Expense.objects.annotate(
            truncated_date=TruncDate('date')
        ).filter(
            truncated_date=today,
            type=expense_type,
            deleted__isnull=True
        )

        # Serializar los gastos
        serializer = ExpenseSerializer(expenses_today, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ExpensesByDateRangeViewSet(viewsets.ViewSet):
    
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
            # Convertir los parámetros a objetos de tipo fecha
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


        # Filtrar los gastos por el rango de fechas
        expenses = Expense.objects.filter(date__gte=start_datetime, date__lte=end_datetime)
        
        # Serializar los datos
        serializer = ExpenseSerializer(expenses, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
