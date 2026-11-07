# Turnos, reservas y profesores

Volver al [índice](README.md).

## Estudios y salas

### `/studios/`

CRUD de los estudios (sedes).

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `name` | Nombre de la sede. |
| `address` | Dirección. |
| `is_active` | Si está operativa. |

### `/rooms/`

CRUD de las salas de cada estudio.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `studio` | Estudio al que pertenece. |
| `name` | Nombre de la sala. |
| `capacity` | Cantidad de lugares. |
| `is_active` | Si se puede usar. |

## Turnos

Un **turno** (`slot`) es una clase en una fecha y hora concretas, en una sala y para una actividad. Los turnos no se cargan uno por uno: se definen **plantillas** semanales y a partir de ellas se generan los turnos de un rango de fechas.

### `/slot-templates/`

CRUD de plantillas de turnos. Por ejemplo: "Reformer, lunes y miércoles de 9 a 10, Sala A, 6 lugares".

**Roles:** Super, Administrador

| Campo | Descripción |
|---|---|
| `days_of_week` | Días de la semana en los que se repite. |
| `start_time`, `end_time` | Horario (`HH:MM`). |
| `room` | Sala. |
| `activity_subtype` | Actividad. |
| `availability` | Cupo. |
| `is_active` | Si se usa para generar turnos. |

### `POST /generate-slots/`

Crea los turnos de una plantilla para un rango de fechas. No duplica los que ya existen y saltea los días que son feriado.

**Roles:** Super, Administrador

**Body**

```json
{
  "template_id": 3,
  "date_from": "2026-11-01",
  "date_to": "2027-02-28"
}
```

**Respuesta 201:** cantidad de turnos creados y omitidos.

**Errores**

| Código | Cuándo |
|---|---|
| `400` | Fechas con formato inválido o `date_from` posterior a `date_to`. |
| `400` | El rango no llega a cubrir 3 meses desde hoy (es el mínimo para que la agenda no quede corta). |
| `400` | La plantilla está inactiva o su cupo supera la capacidad actual de la sala. |
| `404` | La plantilla no existe. |

### `/slots/`

CRUD de turnos.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `template` | Plantilla de la que salió (puede ser nulo si se cargó a mano). |
| `date` | Fecha. |
| `start_time`, `end_time` | Horario. |
| `room` | Sala. |
| `activity_subtype` | Actividad. |
| `availability` | Cupo. |
| `status` | Estado del turno. |

**Acción extra**

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/slots/{id}/restore/` | Vuelve a habilitar un turno dado de baja. No deja hacerlo si la fecha sigue siendo feriado. |

### `GET /available-slots/`

Turnos habilitados, ordenados por día y hora.

**Roles:** Super, Administrador, Consultor

### `GET /calendar/?date_from=AAAA-MM-DD&date_to=AAAA-MM-DD`

Turnos del rango agrupados por fecha, cada uno con sus reservas. Es lo que usa la agenda del front. Si no se mandan fechas, devuelve desde hoy hasta dentro de 6 días.

**Roles:** Super, Administrador, Consultor

**Respuesta 200 (resumen)**

```json
[
  {
    "date": "2026-11-03",
    "slots": [
      {
        "id": 41,
        "start_time": "09:00",
        "end_time": "10:00",
        "week_day_name": "Martes",
        "room_name": "Sala A",
        "studio_name": "Studio Central",
        "activity": "Reformer",
        "availability": 3,
        "capacity": 6,
        "status_name": "disponible",
        "appointments": [
          { "id": 210, "person_id": 15, "person_name": "Laura Fernández", "person_photo": null, "reserved": false }
        ]
      }
    ]
  }
]
```

### `/fixed-slots/`

Turnos fijos: un alumno que viene siempre el mismo día y horario. Al crearlo se generan sus reservas en todos los turnos de la plantilla dentro del rango de fechas.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

**Filtros:** `?person={id}`, `?template={id}`

| Campo | Descripción |
|---|---|
| `person` | Alumno. |
| `template` | Plantilla del turno. |
| `start_date`, `end_date` | Período del turno fijo. |
| `observation` | Nota opcional. |

## Reservas

### `/appointments/`

Reservas de alumnos en turnos. Acepta el [filtro por estudio](README.md#filtro-por-estudio).

**Roles:** Super, Administrador, Consultor y Estudiante. El alumno solo ve y gestiona sus propias reservas.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/appointments/` | Lista de reservas. |
| POST | `/appointments/` | Reserva un lugar. |
| GET | `/appointments/{id}/` | Detalle. |
| PUT / PATCH | `/appointments/{id}/` | Cambia la reserva (por ejemplo, de turno). |
| DELETE | `/appointments/{id}/?code=1234` | Elimina la reserva. |
| POST | `/appointments/{id}/cancel/` | Cancela la reserva. |

**Body para reservar**

```json
{
  "person": 15,
  "slot": 41,
  "code": "1222"
}
```

El `code` es obligatorio cuando reserva el personal. Cuando reserva el alumno desde la app no hace falta.

**Qué hace al reservar**

1. Revisa que el alumno no esté ya anotado en ese turno.
2. Revisa que quede cupo.
3. Busca un plan vigente del alumno que cubra la actividad y le descuenta una sesión.

**Cancelación**

- El alumno puede cancelar hasta 2 horas antes de la clase. El límite se configura con la variable `CANCEL_HOURS_LIMIT`.
- El personal puede cancelar siempre.
- Al cancelar se devuelve la sesión al plan y, si hay alguien en lista de espera, se le avisa por WhatsApp.

**Errores**

| Código | Mensaje |
|---|---|
| `400` | `La persona ya está registrada en ese turno.` |
| `400` | `El cupo en este horario está lleno.` |
| `400` | `No te quedan sesiones en tu plan para esta actividad.` |
| `400` | Fuera del plazo de cancelación (solo alumnos). |

### `GET /upcoming-appointments/` y `GET /past-appointments/`

Reservas futuras y pasadas. El personal puede filtrar con `?person_id={id}`; el alumno ve solo las suyas.

**Roles:** Super, Administrador, Consultor, Estudiante

### `GET /enrollment-check/?person={id}&slot={id}`

Antes de reservar, dice si el alumno tiene un plan que cubra la actividad del turno.

**Roles:** Super, Administrador, Consultor, Estudiante

```json
{ "covered": true, "active_plan": { "id": 7, "sessions_remaining": 5, "exp_date": "2026-11-30" } }
```

Si `covered` es `false` devuelve `required_plans_type` con los planes que tendría que contratar.

## Lista de espera

### `/waiting-list/`

CRUD de la lista de espera de turnos completos. Cuando se libera un lugar se avisa por WhatsApp a quienes están anotados.

**Roles:** Super, Administrador, Consultor

| Campo | Descripción |
|---|---|
| `person` | Alumno. |
| `slot` | Turno. |

## Feriados

### `/holidays/`

CRUD de feriados y días sin actividad.

**Roles:** Super, Administrador, Consultor

| Campo | Descripción |
|---|---|
| `name` | Motivo. |
| `start_date`, `end_date` | Rango del feriado. |

**Efectos sobre los turnos**

- Al crear un feriado se dan de baja los turnos de esas fechas que no tienen reservas. Los que sí tienen reservas no se tocan y vienen informados en la respuesta, para resolverlos a mano.
- Si se edita el feriado y el rango se achica, se vuelven a generar los turnos de los días que quedaron libres.

## Declaración jurada de salud

Antes de tomar clases, cada alumno firma una declaración jurada de salud.

### `/sworn-statement/`

Texto de la declaración. Se guardan versiones: la última activa es la que se muestra.

**Roles:** lectura pública (se muestra en el registro); escritura para Super y Administrador.

### `/person-sworn-statement/`

Firma general del alumno.

**Roles:** el alumno firma la suya; el personal ve el listado.

**Body:** `{ "user_id": 31, "statement": 2 }`

### `/appointment-sworn-statement/`

Firma de la declaración para una clase puntual. Filtro: `?appointment={id}`.

**Body:** `{ "appointment": 210, "statement": 2 }`. Un alumno solo puede firmar para sus propias reservas.

## Profesores

### `/teachers/`

CRUD de profesores. Al dar de baja un profesor también se dan de baja sus asignaciones a turnos y sus horas.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `name`, `last_name`, `dni`, `email`, `phone`, `sex`, `birth_date` | Datos personales. |
| `hours` | Horas pactadas. |

### `/teachers-turn/`

Asigna profesores a turnos. Acepta el [filtro por estudio](README.md#filtro-por-estudio).

**Roles:** Super, Administrador

| Campo | Descripción |
|---|---|
| `teacher` | Profesor. |
| `slot` | Turno. |
| `rol` | Rol en la clase (por ejemplo, titular o asistente). |
| `is_receptionist` | Si cubre recepción en ese horario. |

**Errores:** `400` si el profesor ya está asignado a ese turno con el mismo rol.

### `/hour_view/`

Resumen mensual de horas por profesor: horas pactadas, extra, total y restantes.

**Roles:** Super, Administrador

### `/extra-hours/`

CRUD de horas extra. Cada registro es un turno que el profesor dio fuera de lo pactado y su valor.

**Roles:** Super, Administrador

| Campo | Descripción |
|---|---|
| `teacher` | Profesor. |
| `slot` | Turno. |
| `price` | Monto a pagar. |

### `GET /teacher-extra-hours/{teacher_id}/`

Horas extra de un profesor.

**Roles:** Super, Administrador
