"""Filtro opcional por estudio, común a todos los endpoints.

Query param: ``?studio=<id>``. Admite uno o varios estudios:
``?studio=1,2`` o ``?studio=1&studio=2`` (se pueden combinar).

- Sin el parámetro: no se filtra (comportamiento previo, sin cambios).
- Formato inválido (``abc``, ``-1``, ``0``, vacío, ``1,``)  -> 400.
- Algún id que no corresponde a un estudio                -> 404.
- Estudio dado de baja (soft-delete): se filtra igual (para consultar datos
  históricos de un estudio cerrado) y el listado se devuelve envuelto en
  ``{"detail": "...dado de baja...", "results": [...]}``.

Los permisos NO se tocan acá: siguen siendo los ``permission_classes`` por rol
de cada endpoint (Super / Administrador / Consultor), que DRF evalúa antes.
"""
import re

from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from .models import Studio

STUDIO_PARAM = 'studio'
_POSITIVE_INT = re.compile(r'^[1-9][0-9]*$')
# Un id fuera del rango de un IntegerField de Postgres no puede existir: se
# responde 404 en vez de dejar que la base tire un error (500).
_MAX_DB_INT = 2147483647


class InvalidStudioParam(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El parámetro 'studio' debe ser un número entero positivo."
    default_code = 'invalid_studio'


def parse_studio_ids(request):
    """Valida el formato del parámetro. Devuelve ``None`` si no vino, o la
    lista de ids (sin duplicados, en el orden recibido). 400 si es inválido."""
    if STUDIO_PARAM not in request.query_params:
        return None
    ids = []
    for raw in request.query_params.getlist(STUDIO_PARAM):
        for part in raw.split(','):
            part = part.strip()
            if not _POSITIVE_INT.match(part):
                raise InvalidStudioParam()
            value = int(part)
            if value not in ids:
                ids.append(value)
    return ids


def resolve_studios(request):
    """Formato (400) y existencia (404) de los estudios pedidos.

    Devuelve ``None`` si no se pidió filtro, o la lista de ``Studio``. Incluye
    los dados de baja (``all_objects``): existen y se pueden consultar."""
    ids = parse_studio_ids(request)
    if ids is None:
        return None
    valid_ids = [i for i in ids if i <= _MAX_DB_INT]
    found = {s.pk: s for s in Studio.all_objects.filter(pk__in=valid_ids)}
    for studio_id in ids:
        if studio_id not in found:
            raise NotFound(f"No existe un estudio con id {studio_id}.")
    return [found[i] for i in ids]


def deleted_studios_detail(studios):
    """Mensaje si alguno de los estudios pedidos está dado de baja; si no, None."""
    if not studios:
        return None
    deleted = [s for s in studios if s.deleted is not None]
    if not deleted:
        return None
    if len(deleted) == 1:
        return f"El estudio con id {deleted[0].pk} está dado de baja."
    ids = ', '.join(str(s.pk) for s in deleted)
    return f"Los estudios con id {ids} están dados de baja."


def add_deleted_notice(data, studios):
    """Agrega el aviso de estudio dado de baja a una respuesta 200.
    Objeto -> se agrega "detail". Lista -> se envuelve en {"detail", "results"}."""
    detail = deleted_studios_detail(studios)
    if not detail:
        return data
    if isinstance(data, dict):
        return {**data, "detail": detail}
    return {"detail": detail, "results": data}


class StudioNoticeMixin:
    """Para ViewSets que resuelven el filtro a mano (p. ej. estadísticas):
    si se guardó la lista de estudios en ``request.studio_filter``, agrega el
    aviso de estudio dado de baja a las respuestas exitosas."""

    def finalize_response(self, request, response, *args, **kwargs):
        studios = getattr(request, 'studio_filter', None)
        if studios and 200 <= response.status_code < 300 and getattr(response, 'data', None) is not None:
            response.data = add_deleted_notice(response.data, studios)
        return super().finalize_response(request, response, *args, **kwargs)


class StudioFilterMixin:
    """Mixin para ViewSets de DRF.

    - ``studio_lookup``: camino hasta el FK a Studio (``'studio'`` o
      ``'slot__room__studio'``). Son FKs hacia adelante, así que el join no
      duplica filas y no hace falta ``distinct()``.
    - En ``get_queryset`` del ViewSet: ``return self.filter_by_studio(qs)``.
    - ``list`` envuelve la respuesta si algún estudio está dado de baja.
    - ``studio_filter_enabled()`` permite desactivar el filtro para algún
      usuario (p. ej. alumnos en /appointments/): se ignora el parámetro.
    """
    studio_lookup = 'studio'

    def studio_filter_enabled(self):
        return True

    def get_requested_studios(self):
        if not self.studio_filter_enabled():
            return None
        if not hasattr(self, '_requested_studios'):
            self._requested_studios = resolve_studios(self.request)
        return self._requested_studios

    def filter_by_studio(self, queryset):
        studios = self.get_requested_studios()
        if studios is None:
            return queryset
        return queryset.filter(**{f'{self.studio_lookup}__in': [s.pk for s in studios]})

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        detail = deleted_studios_detail(self.get_requested_studios())
        if detail:
            response.data = {"detail": detail, "results": response.data}
        return response
