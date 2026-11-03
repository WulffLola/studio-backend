# Alumnos, planes y actividades

Volver al [índice](README.md).

## Alumnos

### `/people/`

Fichas de los alumnos del estudio. Un alumno puede existir sin cuenta de usuario: la recepción lo carga y, si después se registra en la app, la cuenta se vincula a esta ficha por DNI.

**Roles:** Super, Administrador, Consultor

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/people/` | Lista de alumnos activos con sus planes vigentes. |
| POST | `/people/` | Alta de alumno. |
| GET | `/people/{id}/` | Ficha del alumno. |
| PUT / PATCH | `/people/{id}/` | Edición. |
| DELETE | `/people/{id}/?code=1234` | Baja del alumno. |
| PATCH | `/people/{id}/upload-photo/` | Sube la foto de perfil (`multipart/form-data`, campo `profile_photo`). |

**Campos**

| Campo | Tipo | Obligatorio al crear | Descripción |
|---|---|---|---|
| `name`, `last_name` | string | Sí | |
| `dni` | string (8) | Sí | |
| `email` | email | Sí | |
| `phone` | string (11) | Sí | Se usa para los avisos por WhatsApp. |
| `sex` | string | Sí | |
| `birth_date` | fecha | Sí | `AAAA-MM-DD`. |
| `observation` | string | No | Notas internas (lesiones, preferencias, etc.). |
| `code` | string | Sí | [Código de operador](README.md#código-de-operador). |
| `active_plans` | lista | Solo lectura | Planes vigentes con sesiones restantes y vencimiento. |
| `firmo_declaracion_general` | bool | Solo lectura | Si ya firmó la [declaración jurada](03-turnos-reservas-profesores.md#declaración-jurada-de-salud). |

**Ejemplo de alta**

```json
POST /people/
{
  "name": "Laura",
  "last_name": "Fernández",
  "dni": "40123456",
  "email": "laura@mail.com",
  "phone": "2914556677",
  "sex": "F",
  "birth_date": "1995-04-12",
  "code": "1222"
}
```

**Errores:** `400` si falta algún campo obligatorio (la respuesta lista cuáles) o si el código de operador no existe.

### `GET /deleted-people/`

Alumnos dados de baja. Se usa para el historial de bajas.

**Roles:** Super, Administrador, Consultor

**Parámetros:** `date_from`, `date_to` (opcionales, `AAAA-MM-DD`) para filtrar por fecha de baja.

### `/person-active-plan/`

CRUD de los planes asignados a cada alumno. Cada registro guarda el plan, la fecha de vencimiento y cuántas sesiones le quedan. Normalmente se crean solos al registrar un pago.

**Roles:** Super, Administrador, Consultor

| Campo | Descripción |
|---|---|
| `person` | Alumno. |
| `plans_subtype` | Plan contratado. |
| `exp_date` | Vencimiento. |
| `sessions_total` | Sesiones que incluye. |
| `sessions_remaining` | Sesiones que le quedan. Baja con cada clase tomada. |

### `GET /person-last-plan/?person={id}`

Último plan registrado del alumno y si sigue activo. Se usa al cargar un pago para sugerir la renovación.

**Roles:** Super, Administrador, Consultor

## Planes

Los planes tienen dos niveles:

- **Tipo de plan** (`/plans-type/`): la categoría, por ejemplo "Mensual 2 veces por semana".
- **Subtipo de plan** (`/plans-subtype/`): el plan concreto que se vende, con su cantidad de sesiones y la actividad a la que da acceso.

### `/plans-type/`

CRUD de tipos de plan.

**Roles:** lectura para todos los roles (incluido Estudiante); escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `name` | Nombre. |
| `quantity` | Cantidad total de clases. |
| `frequency` | Frecuencia, por ejemplo `semanal`. |

### `/plans-subtype/`

CRUD de planes concretos.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `name` | Nombre del plan. |
| `plan_type` | Tipo de plan al que pertenece. |
| `sessions` | Clases incluidas. |
| `activity_subtype` | Actividad a la que da acceso (por ejemplo Reformer). |

### `/payment-amount/`

Precios de cada plan según el medio de pago (efectivo, transferencia, etc.). Un mismo plan puede tener un precio distinto por medio.

**Roles:** Super, Administrador, Consultor

| Campo | Descripción |
|---|---|
| `plans_subtype` | Plan. |
| `method` | Medio de pago. |
| `amount` | Precio. |

**Errores:** `400` si ya existe un precio para ese plan y ese medio de pago.

### `GET /prices/`

Lista pública de planes con su precio, tipo y actividades. La usa la web del estudio y la app antes de loguearse.

**Roles:** público

### `GET /prices/combo-preview/?plans=1,2`

Calcula el precio final de una combinación de planes aplicando los combos de descuento que correspondan.

**Roles:** público

**Respuesta 200 (resumen)**

```json
{
  "plans": [ { "id": 1, "name": "Reformer 2x", "amount": "30000" }, { "id": 2, "name": "Mat 1x", "amount": "15000" } ],
  "applied_combos": [ { "name": "Reformer + Mat", "discount_pct": "10.00" } ],
  "total": "40500"
}
```

**Errores:** `400` si falta `plans` o tiene un formato inválido.

### `GET /available-plans/`

Planes activos con sus actividades, más los combos vigentes. La usa la app de alumnos para mostrar qué se puede contratar.

**Roles:** público

## Descuentos

### `/plan-discount/`

Descuento fijo sobre un plan puntual.

**Roles:** Super, Administrador

| Campo | Descripción |
|---|---|
| `plans_subtype` | Plan. |
| `discount_pct` | Porcentaje de descuento. |

### `/combo-plan-discount/`

Descuento que se aplica cuando el alumno contrata varios planes juntos.

**Roles:** lectura para todos los roles; escritura para Super y Administrador.

| Campo | Descripción |
|---|---|
| `name` | Nombre del combo. |
| `plans` | Lista de planes que lo forman. |
| `discount_pct` | Porcentaje de descuento. |

## Actividades

Igual que los planes, las actividades tienen dos niveles: el **tipo** (por ejemplo Pilates) y el **subtipo** (Reformer, Mat, Barre).

### `/activity-type/`

CRUD de tipos de actividad. Acepta una imagen en el campo `photo` (`multipart/form-data`) que se muestra en la app.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

### `/activity-subtype/`

CRUD de subtipos de actividad.

**Roles:** lectura para todos los roles; escritura para Super, Administrador y Consultor.

| Campo | Descripción |
|---|---|
| `name` | Nombre. |
| `activity_type` | Tipo de actividad al que pertenece. |
