# Documentación de la API

La API de STUDIO es REST y está hecha con Django REST Framework. Todas las respuestas son JSON salvo la descarga de comprobantes, que devuelve un PDF.

## Índice

1. [Autenticación y usuarios](01-autenticacion-y-usuarios.md)
2. [Alumnos, planes y actividades](02-alumnos-planes-actividades.md)

## Convenciones

### URL base

En local, con Docker levantado: `http://localhost:8000/`

Todas las rutas terminan en `/`. Por ejemplo `GET /people/` o `GET /people/12/`.

### Autenticación

Casi todos los endpoints piden un token JWT en el header:

```
Authorization: Bearer <access_token>
```

El token se obtiene en `POST /login/` (ver [autenticación](01-autenticacion-y-usuarios.md)). El access dura 12 horas y el refresh 14 días.

### Roles

Cada usuario tiene un tipo que define qué puede hacer:

| Rol | Qué puede hacer |
|---|---|
| **Super** | Todo. Es el rol de quien administra la plataforma. |
| **Administrador** | Todo lo operativo del estudio: alumnos, turnos, pagos, profesores, estadísticas. |
| **Consultor** | Recepción: carga alumnos, reservas y pagos, pero no ve estadísticas financieras ni configura turnos. |
| **Estudiante** | Solo ve su información, reserva y cancela sus clases. |

En cada tabla de endpoints la columna **Roles** indica quién puede usarlo. Si un rol no tiene permiso, la API responde `403`.

### CRUD estándar

Cuando un recurso dice "CRUD" tiene estas cinco operaciones:

| Método | Ruta | Acción |
|---|---|---|
| GET | `/recurso/` | Lista |
| POST | `/recurso/` | Crea |
| GET | `/recurso/{id}/` | Detalle |
| PUT / PATCH | `/recurso/{id}/` | Modifica (completo / parcial) |
| DELETE | `/recurso/{id}/` | Da de baja |

### Bajas lógicas

Los registros no se borran de la base: al eliminarlos se completa el campo `deleted` con la fecha. Los listados solo devuelven los registros activos.

### Código de operador

Las operaciones sensibles (alta, edición y baja de alumnos, pagos, gastos y reservas hechas desde recepción) piden un campo `code` en el body. Es el código personal de quien hace la operación y queda guardado en el registro de acciones (`/actions/`). Si el código no existe la API responde `400`.

### Filtro por estudio

Los recursos que dependen de una sede (reservas, pagos, gastos, turnos de profesores y la mayoría de las estadísticas) aceptan el parámetro `studio`:

```
GET /payments/?studio=1
GET /payments/?studio=1,2
```

- Si no se manda, se devuelven todos los estudios.
- Si el formato es inválido responde `400`, y si algún id no existe responde `404`.
- Si alguno de los estudios pedidos está dado de baja, la respuesta igual es `200` pero incluye un aviso.

### Errores

| Código | Cuándo |
|---|---|
| `400` | Faltan datos, el formato es inválido o no se cumple una regla de negocio. El body trae `detail` o el error por campo. |
| `401` | No se mandó token o está vencido. |
| `403` | El rol del usuario no tiene permiso. |
| `404` | El recurso no existe o está dado de baja. |

### Documentación interactiva

Con el servidor levantado y un usuario Super logueado:

- Swagger: `/doc&test/`
- Redoc: `/snippets/`
