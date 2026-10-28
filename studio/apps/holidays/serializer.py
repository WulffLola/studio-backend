from datetime import date
from rest_framework import serializers
from .models import Holiday


class HolidaySerializer(serializers.ModelSerializer):

    class Meta:
        model = Holiday
        fields = ['id', 'name', 'start_date', 'end_date', 'deleted']

    def validate(self, data):
        start = data.get('start_date') or getattr(self.instance, 'start_date', None)
        end = data.get('end_date') or getattr(self.instance, 'end_date', None)

        if end and start and end < start:
            raise serializers.ValidationError(
                {'end_date': 'end_date must be greater than or equal to start_date.'}
            )

        if start:
            self._validate_no_overlap(start, end)

        return data

    def _validate_no_overlap(self, start, end):
        """
        Verifica que el rango [start, end] no se solape con ningún feriado
        activo del mismo año.
        Un día único (end=None) se trata como [start, start].
        """
        effective_end = end or start
        year = start.year

        qs = Holiday.objects.filter(
            start_date__year=year,
            deleted__isnull=True,
        )

        # Al editar, excluir el propio registro
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        for holiday in qs:
            h_end = holiday.end_date or holiday.start_date
            # Solapamiento: los rangos se cruzan si start <= h_end AND effective_end >= h_start
            if start <= h_end and effective_end >= holiday.start_date:
                raise serializers.ValidationError(
                    {
                        'start_date': (
                            f'Las fechas se solapan con "{holiday.name}" '
                            f'({holiday.start_date} → {h_end}).'
                        )
                    }
                )
