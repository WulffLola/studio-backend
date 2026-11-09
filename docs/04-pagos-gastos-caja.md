# Pagos, gastos y caja

Volver al [índice](README.md).

## Pagos

### `/payments/`

Cobros a alumnos. Un pago puede incluir uno o varios planes (ítems). Acepta el [filtro por estudio](README.md#filtro-por-estudio).

**Roles:** Super, Administrador, Consultor

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/payments/` | Lista de pagos con sus ítems. |
| POST | `/payments/` | Registra un pago. |
| GET | `/payments/{id}/` | Detalle. |
| PUT / PATCH | `/payments/{id}/` | Corrige un pago. |
| DELETE | `/payments/{id}/?code=1234` | Anula el pago. |
| GET | `/payments/download/{id}/` | Descarga el comprobante en PDF. |

**Body para registrar un pago**

```json
{
  "person": 15,
  "studio": 1,
  "method": "Transferencia",
  "observation": "Pagó dos planes juntos",
  "code": "1222",
  "items": [
    { "plans_subtype_id": 4, "base_amount": "30000" },
    { "plans_subtype_id": 7, "base_amount": "15000" }
  ]
}
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `person` | Sí | Alumno que paga. |
| `items` | Sí | Planes que paga, cada uno con su precio de lista. |
| `code` | Sí | [Código de operador](README.md#código-de-operador). |
| `method` | No | Medio de pago. |
| `studio` | No | Sede donde se cobró. |
| `date` | No | Fecha del pago. Si no se manda, se usa la actual. |
| `observation` | No | Nota interna. |

**Qué hace al registrar un pago**

1. Revisa que los planes tengan clases disponibles para reservar.
2. Aplica el mayor descuento que corresponda a cada ítem (descuento por plan o combo).
3. Guarda el pago con el total y un ítem por plan.
4. Crea o renueva los planes activos del alumno con sus sesiones y vencimiento.
5. Genera el comprobante PDF y, si WhatsApp está configurado, se lo manda al alumno.

**Errores**

| Código | Cuándo |
|---|---|
| `400` | Falta `items` o algún ítem no tiene `plans_subtype_id` y `base_amount`. |
| `400` | Un monto o un plan no son válidos. |
| `400` | `No hay clases disponibles para los siguientes planes.` Viene la lista en `planes_sin_clases`. |
| `400` | El código de operador no existe. |
| `404` | Al descargar, el PDF no existe. |

### `/payment-items/`

CRUD de los ítems de pago (un plan dentro de un pago).

**Roles:** Super, Administrador, Consultor

| Campo | Descripción |
|---|---|
| `payment` | Pago al que pertenece. |
| `plans_subtype` | Plan. |
| `base_amount` | Precio de lista. |
| `discount_pct` | Descuento aplicado. |
| `discount_source` | Origen del descuento (`none`, `plan`, `combo`). |
| `final_amount` | Precio cobrado. |

### `POST /compute-discount/`

Calcula descuentos sin registrar nada. El front lo usa para mostrar el total antes de confirmar el cobro.

**Roles:** Super, Administrador, Consultor

**Body:** `[ { "plans_type_id": 1, "base_amount": "30000" } ]`

**Respuesta 200:** los mismos ítems con `discount_pct` y `final_amount`.

### Consultas de pagos

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| GET | `/payments-today/` | Pagos de hoy. | Super, Administrador, Consultor |
| GET | `/payments-by-day-range/?start_date=&end_date=` | Pagos de un rango de fechas. | Super, Administrador |
| GET | `/payments-last-month/` | Pagos del último mes y medio. | Super, Administrador, Consultor |
| GET | `/overdue-payments/` | Planes de alumnos ya vencidos. Filtro opcional `?person_id=`. | Super, Administrador, Consultor |

Las fechas van en formato `AAAA-MM-DD`.

## Gastos

### `/expenses/`

Gastos del estudio. Acepta el [filtro por estudio](README.md#filtro-por-estudio).

**Roles:** Super, Administrador, Consultor

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/expenses/` | Lista de gastos. |
| POST | `/expenses/` | Registra un gasto. |
| GET | `/expenses/{id}/` | Detalle. |
| PUT / PATCH | `/expenses/{id}/` | Modifica. |
| DELETE | `/expenses/{id}/?code=1234` | Anula. |

| Campo | Obligatorio | Descripción |
|---|---|---|
| `type_id` | Sí | Tipo de gasto (ver `/expense-type/`). |
| `amount` | No | Monto. Puede ser `0`. |
| `studio` | Sí | Sede. |
| `teacher` | Solo para sueldos | Profesor al que se le paga, cuando el tipo es "Sueldo". |
| `method` | No | Medio de pago. |
| `observation` | No | Detalle. |
| `code` | Sí | [Código de operador](README.md#código-de-operador). |

La fecha se completa sola con el momento en que se registra.

**Errores:** `400` si falta `type_id` o el `teacher` en un sueldo; `404` si el tipo de gasto o el profesor no existen.

### `/expense-type/`

CRUD de tipos de gasto (alquiler, sueldos, insumos, gastos chicos, etc.). No permite nombres repetidos: si ya existe uno igual responde `400`.

**Roles:** Super, Administrador, Consultor

### Consultas de gastos

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| GET | `/total-expenses/?start_date=&end_date=` | Total gastado en el rango. | Super, Administrador, Consultor |
| GET | `/expenses_by_range/?start_date=&end_date=` | Gastos del rango. | Super, Administrador |
| GET | `/expenses_today_teachers/` | Gastos chicos del día (los que maneja recepción). | Super, Administrador, Consultor |

## Caja

La caja junta pagos y gastos en un solo listado ordenado por hora, como un libro diario.

| Método | Ruta | Descripción | Roles |
|---|---|---|---|
| GET | `/cash_journal/?start_date=&end_date=` | Movimientos de un rango de fechas. | Super, Administrador |
| GET | `/cash_journal_today/` | Movimientos de hoy. | Super, Administrador, Consultor |
| GET | `/teacher_cash_journal_today/` | Movimientos de hoy que maneja recepción. | Super, Administrador, Consultor |

**Errores en los rangos de fechas**

| Código | Mensaje |
|---|---|
| `400` | `Se requieren las fechas 'start_date' y 'end_date'.` |
| `400` | `Formato de fecha inválido. Use YYYY-MM-DD.` |
| `400` | `'start_date' debe ser anterior o igual a 'end_date'.` |
