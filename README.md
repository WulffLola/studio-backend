# STUDIO · Backend

API REST de **STUDIO**, una plataforma para la gestión operativa de estudios de Pilates. Centraliza en un solo sistema lo que en muchos estudios se maneja con planillas, cuadernos y mensajes sueltos: alumnos, planes, turnos, reservas, profesores, pagos y caja.

La interfaz web está en el proyecto `studio-frontend`.

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
    ├── data_seed/          # fixtures JSON antiguos (los datos de prueba se generan con seed_all)
    └── conftest.py         # fixtures compartidas de los tests
```

Cada app sigue la misma organización: `models.py`, `serializer.py`, `views.py`, `tests.py` y sus migraciones. La lógica de negocio que se reutiliza entre vistas está en `services.py`.

## Cómo levantarlo

### 1. Requisitos

- **Docker Desktop** (Windows o Mac) o Docker Engine + Docker Compose (Linux). Se descarga de https://www.docker.com/products/docker-desktop/
- Abrir Docker Desktop y esperar a que indique que está corriendo (*Engine running*) antes de seguir.
- El puerto `8000` libre.

No hace falta instalar Python ni PostgreSQL: todo corre dentro de los contenedores.

### 2. Obtener el código

```bash
git clone https://github.com/WulffLola/studio-backend.git
cd studio-backend
```

O descomprimir `studio-backend.zip` y abrir una terminal dentro de la carpeta `studio-backend`.

### 3. Levantar

```bash
cd docker
cp .env.example .env
docker compose up -d --build
```

En Windows con CMD se usa `copy .env.example .env` en lugar de `cp`.

La primera vez tarda varios minutos porque descarga las imágenes e instala las dependencias. Al iniciar, el contenedor corre las migraciones.

Para ver que terminó de arrancar:

```bash
docker compose logs -f studio_testing_backend
```

Cuando aparece `Starting development server at http://0.0.0.0:8000/`, se corta con `Ctrl+C` (los contenedores siguen corriendo).

El backend espera a que la base de datos esté lista antes de arrancar, así que los primeros segundos puede no mostrar nada.

### 4. Cargar los datos de prueba

```bash
docker compose exec studio_testing_backend python manage.py seed_all
```

Vacía la base y genera un sistema completo con datos ficticios y fechas alrededor de hoy: 2 sedes (*Aura Casanova* y *Aura Colón*) con 3 salas, plantillas de horario y clases desde 8 semanas atrás hasta 3 semanas adelante, 9 profesoras con sus turnos y horas, unos 60 alumnos con planes, turnos fijos, reservas y algunas bajas, pagos, gastos, notas, recetas y publicaciones. Tarda unos segundos y se puede volver a correr para empezar de cero.

Usuarios para entrar (todos con la contraseña `studio1234`):

| Usuario | Rol | Código de acciones |
|---|---|---|
| `super@studio.local` | Super | `1111` |
| `admin@studio.local` | Administrador | `2222` |
| `recepcion@studio.local` | Consultor | `3333` |

El Consultor (recepción) puede dar de baja alumnos, pagos y gastos, pero tiene que ingresar su código personal de 4 dígitos: así queda registrado quién lo hizo en *Acciones*.

Para más o menos alumnos: `python manage.py seed_all --alumnos 120`. El comando `seed_demo --reset` carga la versión grande (300 alumnos) que se usa en la demo publicada, con su propio usuario.

### 5. Probar

La API queda en `http://localhost:8000/`. Para obtener un token:

```bash
curl -X POST http://localhost:8000/login/ -H "Content-Type: application/json" \
  -d '{"identifier": "admin@studio.local", "password": "studio1234"}'
```

La respuesta trae `tokens.access`, que se manda en cada pedido como `Authorization: Bearer <token>`.

Para usar la interfaz web, seguir los pasos del README de `studio-frontend`.

### 6. Apagar

```bash
docker compose down
```

Los datos quedan guardados en la carpeta `data_local/`. Para empezar de cero alcanza con volver a correr `seed_all`.

## Instalación sin Docker (opcional)

Requisitos: Python 3.11 y PostgreSQL 13 o superior.

1. Crear el usuario y la base (los valores son los de `docker/.env.example`). El usuario necesita `CREATEDB` para que los tests puedan crear su propia base:

```bash
psql -U postgres -c "CREATE USER studio WITH PASSWORD 'studio' CREATEDB;"
psql -U postgres -c "CREATE DATABASE studio OWNER studio;"
```

2. Instalar las dependencias:

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r docker/requirements.txt
```

3. Cargar las variables de entorno. El proyecto las lee del entorno (no lee archivos `.env` solo), así que hay que cargarlas en la terminal antes de cada comando:

```bash
cp docker/.env.example .env.local
# editar .env.local y cambiar POSTGRES_HOST=db por POSTGRES_HOST=localhost
set -a; source .env.local; set +a
```

En Windows (PowerShell):

```powershell
Get-Content .env.local | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { Set-Item "env:$($matches[1])" $matches[2].Trim('"') } }
```

4. Preparar la base y levantar:

```bash
cd studio
python manage.py migrate
python manage.py collectstatic --noinput   # necesario si DEBUG=false (estilos de Swagger y Redoc)
python manage.py seed_all
python manage.py runserver
```

La API queda en `http://localhost:8000/`, igual que con Docker. En cada terminal nueva hay que volver a cargar las variables (paso 3) antes de usar `manage.py`:

```bash
set -a; source .env.local; set +a
cd studio && python manage.py runserver
```

## Tests

Con los contenedores levantados:

```bash
cd docker
docker compose exec studio_testing_backend pytest
```

Sin Docker: `cd studio && pytest` (con las variables de entorno cargadas).

Tarda unos 2 o 3 minutos. La salida es larga porque `pytest.ini` ya trae `-v`; con `pytest -q` se ve solo el resumen.

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

La referencia de todos los endpoints está en `/doc&test/` (Swagger) y `/snippets/` (Redoc), y solo la puede ver el usuario Super: primero hay que iniciar sesión en `http://localhost:8000/api-auth/login/` con `super@studio.local` / `studio1234` y después abrir `http://localhost:8000/doc&test/`. En [`docs/`](docs/README.md) están las convenciones generales de la API.

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
