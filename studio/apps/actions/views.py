from datetime import datetime, time, timedelta

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response

from .serializer import ActionSerializer
from .models import Action
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

DEFAULT_ACTIONS_WINDOW_DAYS = 30


def resolve_actions_range(date_from, date_to, today, default_days=DEFAULT_ACTIONS_WINDOW_DAYS):
    """Resuelve el rango [start, end] (datetimes aware) para filtrar acciones por
    timestamp. Sin fechas -> últimos `default_days` días. Con ambas (YYYY-MM-DD) ->
    ese rango. Solo una, formato inválido o from>to -> ValueError con el mensaje
    para el 400. Función pura (no depende de DRF)."""
    if not date_from and not date_to:
        start_date = today - timedelta(days=default_days)
        end_date = today
    elif date_from and date_to:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError("Formato de fecha inválido. Utilizá YYYY-MM-DD.")
        if start_date > end_date:
            raise ValueError("'date_from' debe ser anterior o igual a 'date_to'.")
    else:
        raise ValueError("'date_from' y 'date_to' deben enviarse juntos.")

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max))
    return start_dt, end_dt


class ActionsViewSet(viewsets.ModelViewSet):
    serializer_class = ActionSerializer
    permission_classes = [IsAdministrador | IsSuper]

    def get_queryset(self):
        # El detalle (retrieve/update/delete) opera sobre todo el historial;
        # el filtro por fecha se aplica solo en list().
        return Action.objects.all().order_by('-timestamp')

    def list(self, request, *args, **kwargs):
        # No devolver todo el historial por defecto: últimos 30 días, o el rango
        # date_from/date_to si se envía (ambos juntos).
        try:
            start_dt, end_dt = resolve_actions_range(
                request.query_params.get('date_from'),
                request.query_params.get('date_to'),
                timezone.localdate(),
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(timestamp__gte=start_dt, timestamp__lte=end_dt)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
