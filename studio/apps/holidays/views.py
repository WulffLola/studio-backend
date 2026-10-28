import logging
from datetime import date, timedelta

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.actions.models import Action
from apps.slots.services import cancel_unreserved_slots_on_dates, regenerate_slots_on_dates
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

from .models import Holiday
from .serializer import HolidaySerializer

logger = logging.getLogger(__name__)


class HolidayViewSet(viewsets.ModelViewSet):
    serializer_class = HolidaySerializer
    permission_classes = [IsAdministrador | IsConsultor | IsSuper]

    def get_queryset(self):
        year = date.today().year
        return Holiday.all_objects.for_user(self.request.user).filter(
            start_date__year=year,
        )

    def create(self, request, *args, **kwargs):
        """Al crear un feriado, cancela los slots futuros sin reserva en sus
        fechas (los reservados se protegen y se reportan)."""
        response = super().create(request, *args, **kwargs)
        self._cancel_slots_for_holiday(request, response)
        return response

    def update(self, request, *args, **kwargs):
        """Al editar un feriado, cancela los slots sin reserva de las fechas que
        quedan dentro del feriado y, si el rango se ACORTA, regenera los slots de
        las fechas que dejan de ser feriado (`fechas_liberadas`), para que no queden
        horarios perdidos en silencio."""
        instance = self.get_object()
        old_dates = self._range_dates(instance.start_date, instance.end_date)

        response = super().update(request, *args, **kwargs)
        self._cancel_slots_for_holiday(request, response)

        start = response.data.get('start_date')
        if start:
            new_start = date.fromisoformat(str(start))
            new_end_raw = response.data.get('end_date')
            new_end = date.fromisoformat(str(new_end_raw)) if new_end_raw else new_start
            new_dates = self._range_dates(new_start, new_end)
            today = date.today()
            liberadas = sorted(d for d in (old_dates - new_dates) if d >= today)
            if liberadas:
                response.data['fechas_liberadas'] = [d.isoformat() for d in liberadas]
                try:
                    response.data['slots_regenerados'] = regenerate_slots_on_dates(set(liberadas))
                except Exception:
                    logger.exception("Feriado %s acortado, pero falló la regeneración de slots", start)
                    response.data['slots_regenerados'] = None
                    response.data['regeneracion_warning'] = (
                        "El feriado se guardó, pero la regeneración de slots en las "
                        "fechas liberadas falló. Volvé a correr la generación."
                    )

        return response

    @staticmethod
    def _range_dates(start_d, end_d):
        """Set de fechas en [start_d, end_d] (end_d nulo = día único)."""
        end_d = end_d or start_d
        dates = set()
        current = start_d
        one_day = timedelta(days=1)
        while current <= end_d:
            dates.add(current)
            current += one_day
        return dates

    def _cancel_slots_for_holiday(self, request, response):
        """Cancela los slots futuros sin reserva en el rango del feriado presente
        en ``response.data`` y agrega el resumen a la respuesta.

        La cancelación es un paso secundario: si falla, el feriado ya quedó
        persistido y se reporta el problema en vez de devolver 500.
        """
        start = response.data.get('start_date')
        if not start:
            return

        start_d = date.fromisoformat(str(start))
        end_raw = response.data.get('end_date')
        end_d = date.fromisoformat(str(end_raw)) if end_raw else start_d
        dates = self._range_dates(start_d, end_d)

        try:
            cancelados, protegidos = cancel_unreserved_slots_on_dates(dates)
        except Exception:
            logger.exception("Feriado %s guardado, pero falló la cancelación de slots", start)
            response.data['slots_cancelados'] = None
            response.data['slots_protegidos'] = []
            response.data['cancelacion_warning'] = (
                "El feriado se guardó, pero la cancelación de slots falló. "
                "Volvé a correr la generación para limpiar las fechas."
            )
            return

        response.data['slots_cancelados'] = cancelados
        response.data['slots_protegidos'] = protegidos

        if cancelados > 0:
            Action.objects.create(
                user=request.user,
                action="Eliminar",
                target="Slots cancelados por feriado",
                target_id=response.data.get('id'),
                new_value=[
                    {"field": "Feriado", "value": str(response.data.get('name', ''))},
                    {"field": "Rango", "value": f"{start_d} a {end_d}"},
                    {"field": "Slots cancelados", "value": str(cancelados)},
                    {"field": "Slots protegidos", "value": str(len(protegidos))},
                ],
            )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
