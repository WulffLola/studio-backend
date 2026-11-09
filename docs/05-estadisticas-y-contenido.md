# Estadísticas y módulos de contenido

Volver al [índice](README.md).

## Estadísticas

Todos los endpoints de estadísticas son de solo lectura (`GET`). Salvo que se indique otra cosa:

- Las fechas van en formato `AAAA-MM-DD` y son opcionales.
- Aceptan el [filtro por estudio](README.md#filtro-por-estudio) con `?studio=`.

### Finanzas

| Ruta | Qué devuelve | Parámetros | Roles |
|---|---|---|---|
| `/margen-bruto/` | Ingresos, gastos y la diferencia entre ambos (`gross_margin`). | `start_date`, `end_date` (obligatorios) | Super, Administrador |
| `/margen-neto/` | Ingresos menos sueldos pagados (`net_margin`). | `start_date`, `end_date` (obligatorios) | Super, Administrador |
| `/total-expenses-by-type/` | Total gastado por cada tipo de gasto. | `start_date`, `end_date`, `expense_type` | Super, Administrador |
| `/payments-breakdown/` | Ingresos desglosados por medio de pago y por plan. | `start_date`, `end_date` | Super, Administrador |
| `/most-profitable-plan/` | Ranking de planes según lo que facturaron. | `month`, `year` | Super, Administrador |
| `/payment-status-current-month/` | Quiénes pagaron y quiénes no este mes, con nombre y teléfono. | | Super, Administrador, Consultor |

### Alumnos

| Ruta | Qué devuelve | Parámetros | Roles |
|---|---|---|---|
| `/status-clients/` | Alumnos activos e inactivos. | `activity`, `plan` | Super, Administrador, Consultor |
| `/clients-by-month/` | Altas y bajas de alumnos por mes. | | Super, Administrador |
| `/clients-by-plan/` | Cantidad de alumnos en cada plan. | | Super, Administrador |
| `/retention-rate/` | Porcentaje de planes renovados. Un plan cuenta como renovado si el alumno contrata otro de la misma actividad dentro de la ventana. | `window_days` | Super, Administrador |
| `/average-age/` | Edad promedio y distribución por rangos. | `activity`, `start_time` | Super, Administrador |
| `/average-age-by-hour/` | Edad promedio según el horario de las clases. | | Super, Administrador |
| `/tenure/` | Antigüedad de los alumnos activos agrupada por rangos. | | Super, Administrador |
| `/stats-person/` | Resumen de un alumno: clases tomadas, cancelaciones, planes. | `person` (obligatorio) | Super, Administrador, Consultor |

### Planes

| Ruta | Qué devuelve | Parámetros | Roles |
|---|---|---|---|
| `/plan-validity/` | Planes vigentes, vencidos y por vencer según su fecha de vencimiento. | `days_ahead` | Super, Administrador, Consultor |
| `/plan-usage/` | Sesiones usadas y sin usar de los planes, incluidas las que vencieron sin tomarse. | `activity` | Super, Administrador |

### Clases y ocupación

| Ruta | Qué devuelve | Parámetros | Roles |
|---|---|---|---|
| `/peak-hours/` | Horarios con más reservas. | | Super, Administrador |
| `/occupancy-rate/` | Ocupación total del período: reservas sobre cupos. | `start_date`, `end_date` | Super, Administrador |
| `/occupancy-by-hour/` | Ocupación por franja (estudio, sala, actividad, día y hora). | `start_date`, `end_date` | Super, Administrador |
| `/occupancy-evolution/` | Evolución de la ocupación de cada franja período a período. | `start_date`, `end_date`, `granularity` | Super, Administrador |
| `/classes-and-reservations/` | Clases programadas y reservas activas y canceladas, por actividad. | `start_date`, `end_date` | Super, Administrador |
| `/cancellation-rate/` | Tasa de cancelación de reservas del mes. | `month` | Super, Administrador |
| `/waiting-list-stats/` | Solicitudes de lista de espera por horario y cuántas terminaron en reserva. | `start_date`, `end_date` | Super, Administrador, Consultor |
| `/stats-studio/` | Resumen general de un estudio. | `studio` (obligatorio), `start_date`, `end_date` | Super, Administrador |
| `/stats-activity-subtype/` | Resumen por actividad. | `start_date`, `end_date` | Super, Administrador |

**Cómo se calcula la ocupación:** para cada clase, los cupos son los lugares libres más las reservas confirmadas. La ocupación es la suma de reservas dividida por la suma de cupos.

## Recomendaciones

El módulo analiza el historial de ocupación y sugiere cambios en la grilla de horarios. No usa inteligencia artificial: aplica reglas fijas sobre los datos de las últimas semanas.

### `POST /recommendations/analyze/`

Corre un análisis y genera las recomendaciones.

**Roles:** Super, Administrador

**Body** (todos los campos son opcionales)

| Campo | Default | Descripción |
|---|---|---|
| `window_weeks` | 8 | Semanas hacia atrás que se analizan (entre 8 y 12). |
| `min_classes` | 8 | Mínimo de clases de una franja para poder sacar conclusiones. |
| `high_occupancy_threshold` | 0.8 | Desde qué ocupación una clase se considera llena. |
| `high_occupancy_ratio` | 0.6 | Proporción de clases llenas para sugerir agregar un horario. |
| `low_occupancy_threshold` | 0.5 | Hasta qué ocupación una clase se considera floja. |
| `low_occupancy_ratio` | 0.6 | Proporción de clases flojas para sugerir reducir o mover un horario. |

**Respuesta 201:** el análisis creado, con un resumen y sus recomendaciones.

### `GET /recommendations/`

Lista de recomendaciones, de la más nueva a la más vieja.

**Roles:** Super, Administrador

**Filtros:** `state`, `type`, `studio`, `analysis`

| Campo | Descripción |
|---|---|
| `type` | `add` (agregar horario), `relocate` (mover) o `reduce` (reducir). |
| `studio`, `room`, `activity_subtype`, `weekday`, `start_time` | Franja a la que se refiere. |
| `occupancy_avg` | Ocupación promedio de la franja. |
| `waitlist_count` | Personas que quedaron en lista de espera. |
| `rules_applied` | Reglas que dispararon la recomendación. |
| `proposed_alternative` | Horario alternativo sugerido, si corresponde. |
| `state` | `pending`, `accepted` o `discarded`. |

### `POST /recommendations/{id}/accept/` y `POST /recommendations/{id}/discard/`

Registra la decisión sobre una recomendación. La API no modifica la grilla sola: el cambio lo hace el administrador en las plantillas de turnos.

**Roles:** Super, Administrador

**Errores:** `409` si la recomendación ya fue decidida.

### `GET /recommendation-analyses/`

Historial de análisis corridos con sus parámetros.

**Roles:** Super, Administrador

## Contenido para alumnos

Estos módulos alimentan la sección de tips y el inicio de la app de alumnos.

| Ruta | Descripción | Lectura | Escritura |
|---|---|---|---|
| `/notes/` | Notas y consejos con imagen o video. | Todos los roles | Super, Administrador |
| `/recipes/` | Recetas con ingredientes, pasos, imagen o video. | Todos los roles | Super, Administrador |
| `/posts/` | Publicaciones del feed. | Cualquier usuario logueado | Super, Administrador |
| `/home-phrase/` | Frase destacada del inicio. | Todos los roles | Super, Administrador |

**Campos de `/notes/`:** `titulo`, `imagen`, `video`, `estado`.

**Campos de `/recipes/`:** `titulo`, `ingredientes`, `pasos`, `imagen`, `video`, `estado`.

**Campos de `/posts/`:** `title`, `caption`, `image`, `video`, `status`, `published_at`.

**Campos de `/home-phrase/`:** `title`, `phrase`, `is_active`.

Las imágenes y videos se suben con `multipart/form-data`.

## Registro de acciones

### `GET /actions/`

Historial de operaciones hechas en el sistema: quién hizo qué, sobre qué registro y qué valores cambió. Se completa solo cada vez que se usa un [código de operador](README.md#código-de-operador).

**Roles:** Super, Administrador

**Parámetros:** `date_from`, `date_to`

| Campo | Descripción |
|---|---|
| `user` | Quién hizo la operación. |
| `action` | Tipo de operación (alta, edición, baja). |
| `target`, `target_id` | Registro afectado. |
| `old_value`, `new_value` | Valores antes y después. |
| `timestamp` | Fecha y hora. |
