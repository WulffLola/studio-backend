from datetime import timedelta

from .models import Holiday


def holiday_dates_in_range(date_from, date_to):
    """Devuelve el ``set`` de fechas dentro de ``[date_from, date_to]`` que caen
    en algún feriado activo.

    Un ``Holiday`` con ``end_date`` nulo representa un día único; con ``end_date``
    define un rango inclusivo. Los feriados soft-deleteados quedan afuera (el
    manager ``objects`` ya los excluye). Las fechas se recortan a la ventana.
    """
    result = set()
    if date_from > date_to:
        return result

    one_day = timedelta(days=1)
    for holiday in Holiday.objects.filter(start_date__lte=date_to):
        h_end = holiday.end_date or holiday.start_date
        if h_end < date_from:
            continue
        current = max(holiday.start_date, date_from)
        last = min(h_end, date_to)
        while current <= last:
            result.add(current)
            current += one_day
    return result
