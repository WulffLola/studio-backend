# STUDIO · Backend

API REST de **STUDIO**, una plataforma para la gestión operativa de estudios de Pilates. Centraliza en un solo sistema lo que en muchos estudios se maneja con planillas, cuadernos y mensajes sueltos: alumnos, planes, turnos, reservas, profesores, pagos y caja.

La interfaz web está en [studio-frontend](https://github.com/WulffLola/studio-frontend).

## Funcionalidades

- **Alumnos:** ficha completa, planes vigentes con sesiones restantes, historial de bajas y declaración jurada de salud.
- **Planes y precios:** tipos y subtipos de plan, precio por medio de pago, descuentos por plan y combos.
- **Turnos:** plantillas semanales por sala y actividad, generación automática de la agenda, turnos fijos y feriados.
- **Reservas:** control de cupo y de sesiones del plan, cancelación con límite de horas y lista de espera con aviso por WhatsApp.
- **Profesores:** asignación a turnos, horas mensuales y horas extra.
- **Pagos y caja:** cobros con varios planes, comprobante en PDF, gastos por tipo y caja diaria.
- **Estadísticas:** ocupación, retención, márgenes, uso de planes y más de 20 indicadores.
- **Recomendaciones:** análisis por reglas del historial de ocupación para sugerir cambios en la grilla.
- **Multi sede:** todo se puede filtrar por estudio.
- **Roles:** Super, Administrador, Consultor y Estudiante, con permisos distintos en cada endpoint.

## Stack

| | |
|---|---|
| Lenguaje | Python 3.11 |
| Framework | Django 4 + Django REST Framework |
| Base de datos | PostgreSQL 13 |
| Autenticación | JWT (`djangorestframework-simplejwt`) |
| PDFs | ReportLab |
| Tests | pytest + pytest-django |
| Infraestructura | Docker, Docker Compose y nginx |

## Estructura

```
studio-backend/
├── docker/                 # Dockerfiles, compose, nginx y requirements
│   └── .env.example        # variables de entorno de ejemplo
├── docs/                   # documentación de la API
└── studio/
    ├── manage.py
    ├── studio/             # configuración del proyecto (settings, urls)
    ├── apps/               # una app de Django por módulo
    │   ├── people/         # alumnos
    │   ├── plans_type/     # tipos de plan, precios y descuentos
    │   ├── slots/          # plantillas y turnos
    │   ├── appointments/   # reservas
    │   ├── payments/       # pagos, comprobantes y caja
    │   ├── statistics/     # indicadores
    │   ├── recommendations/
    │   └── ...
    ├── data_seed/          # datos de prueba
    └── conftest.py         # fixtures compartidas de los tests
```

Cada app sigue la misma organización: `models.py`, `serializer.py`, `views.py`, `tests.py` y sus migraciones. La lógica de negocio que se reutiliza entre vistas está en `services.py`.

## Instalación con Docker

Requisitos: Docker y Docker Compose.

```bash
git clone https://github.com/WulffLola/studio-backend.git
cd studio-backend/docker
cp .env.example .env        # completar SECRET_KEY y, si hace falta, el resto
docker compose up -d --build
```

La API queda en `http://localhost:8000/`. El contenedor corre las migraciones al iniciar.

### Datos de prueba

```bash
docker compose exec studio_testing_backend python manage.py seed_all
```

Carga estudios, salas, planes, profesores, alumnos, turnos, reservas y pagos de ejemplo. Usuarios para entrar:

| Usuario | Rol | Contraseña |
|---|---|---|
| `super@studio.local` | Super | `studio1234` |
| `admin@studio.local` | Administrador | `studio1234` |
| `recepcion@studio.local` | Consultor | `studio1234` |

## Instalación sin Docker

Requisitos: Python 3.11 y PostgreSQL.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r docker/requirements.txt
```

Exportar las variables de `docker/.env.example` (con `POSTGRES_HOST=localhost`) y después:

```bash
cd studio
python manage.py migrate
python manage.py seed_all
python manage.py runserver
```

## Tests

```bash
cd studio
pytest
```

Para correr los de un módulo: `pytest apps/appointments`.

## Variables de entorno

Todas están en [`docker/.env.example`](docker/.env.example). Las principales:

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave de Django. |
| `DEBUG` | `true` en desarrollo. |
| `POSTGRES_*` | Conexión a la base de datos. |
| `CANCEL_HOURS_LIMIT` | Horas mínimas para que un alumno pueda cancelar una reserva (por defecto 2). |
| `FRONTEND_URL` | URL del front, usada en los links de los emails. |
| `API_WPP_*` | Endpoints del servicio de WhatsApp (opcional). |
| `BREVO_*` | Envío de emails de verificación y recuperación (opcional). |

## Documentación de la API

Con el servidor levantado, la referencia de todos los endpoints está en `/doc&test/` (Swagger) y `/snippets/` (Redoc). En [`docs/`](docs/README.md) están las convenciones generales de la API.

## Tareas programadas

Comandos pensados para correr con cron:

| Comando | Qué hace |
|---|---|
| `python manage.py enviar_mensaje_cumple` | Saluda por WhatsApp a los alumnos que cumplen años. |
| `python manage.py enviar_mensaje_por_vencer` | Avisa a los alumnos cuyo plan vence en 3 días. |
| `python manage.py remover_personas_vencidas` | Da de baja a los alumnos con el plan vencido hace 7 días y les avisa. |
| `python manage.py generate_slots` | Mantiene la agenda generada hasta 3 meses hacia adelante con las plantillas activas. |

## Autora

Lola Wulff
