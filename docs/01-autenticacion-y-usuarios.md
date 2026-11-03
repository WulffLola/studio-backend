# Autenticación y usuarios

Volver al [índice](README.md).

## Login

### `POST /login/`

Login del personal del estudio (Super, Administrador y Consultor). Se puede entrar con email o con DNI.

**Roles:** público

**Body**

```json
{
  "identifier": "super@studio.local",
  "password": "studio1234"
}
```

**Respuesta 200**

```json
{
  "id": 1,
  "email": "super@studio.local",
  "dni": "30111222",
  "name": "Super",
  "last_name": "Studio",
  "code": "1222",
  "profile_photo": null,
  "tipo": "Super",
  "tokens": {
    "refresh": "eyJhbGciOi...",
    "access": "eyJhbGciOi..."
  }
}
```

El `access` es el que se manda en el header `Authorization: Bearer ...` en el resto de las llamadas.

**Errores:** `400` con `"Credenciales incorrectas"` si el usuario no existe, está inactivo o la contraseña no coincide.

### `POST /student-login/`

Igual que `/login/`, pero solo deja entrar a usuarios que son alumnos. Si las credenciales son de un usuario del personal responde `403`. Lo usa la app de alumnos.

**Roles:** público

### `POST /token/refresh/`

Devuelve un access nuevo a partir del refresh.

**Body:** `{ "refresh": "<refresh_token>" }`

**Respuesta 200:** `{ "access": "<nuevo_access>" }`

### `POST /logout/`

Invalida el refresh token para que no se pueda volver a usar.

**Roles:** cualquier usuario logueado

**Body**

| Campo | Tipo | Descripción |
|---|---|---|
| `refresh_token` | string | Token a invalidar. |
| `all` | bool | Opcional. Si es `true` invalida todas las sesiones del usuario. |

## Registro de alumnos

El registro desde la app de alumnos tiene tres pasos: verificar el DNI, crear la cuenta y confirmar el email.

### `POST /register/check/`

Revisa si el DNI y el email ya tienen cuenta o si el alumno ya estaba cargado en el estudio.

**Roles:** público

**Body:** `{ "dni": "40123456", "email": "alumna@mail.com" }`

**Respuesta 200**: el campo `result` puede ser:

| `result` | Significado | Qué hace el front |
|---|---|---|
| `already_registered` | El DNI o el email ya tienen usuario. | Manda al login. |
| `not_found` | El DNI no está cargado en el estudio. | Muestra el registro completo. |
| `email_mismatch` | El DNI existe pero con otro email. | Pide revisar el email. |
| `found` | El DNI existe y el email coincide. Viene `person` con los datos. | Muestra el registro con los datos precargados. |

### `POST /register/`

Crea el usuario alumno y manda el email de verificación.

**Roles:** público

**Body (alumno nuevo)**

| Campo | Obligatorio |
|---|---|
| `dni`, `email`, `password`, `name`, `last_name` | Sí |
| `sex`, `phone`, `birth_date` | No |

**Body (alumno ya cargado en el estudio):** solo `dni`, `email` y `password`. La cuenta queda vinculada a la ficha que ya existe.

**Respuesta 201:** mensaje de confirmación. La cuenta queda inactiva hasta verificar el email.

### `POST /register/verify-email/`

Activa la cuenta con el token que llega por email y devuelve los tokens JWT para entrar directo.

**Roles:** público

**Body:** `{ "token": "<token_del_email>" }`

**Errores:** `400` si el token es inválido o venció.

## Recuperación de contraseña

### `POST /password-reset/`

Manda un email con un enlace para cambiar la contraseña. El enlace dura una hora.

**Roles:** público

**Body:** `{ "email": "alumna@mail.com" }`

**Respuesta 200:** siempre responde lo mismo, exista o no el email, para no revelar qué cuentas existen.

### `POST /password-reset/confirm/`

**Roles:** público

**Body:** `{ "token": "<token_del_email>", "password": "nuevaClave123" }`

**Errores:** `400` si el enlace venció o el token no es válido.

## Usuarios

### `/users/`

CRUD de los usuarios del sistema (personal y alumnos con cuenta).

| Método | Ruta | Roles |
|---|---|---|
| GET | `/users/` | Super, Administrador |
| POST | `/users/` | Super, Administrador |
| GET | `/users/{id}/` | Super, Administrador, Estudiante (el propio) |
| PUT / PATCH | `/users/{id}/` | Super, Administrador, Estudiante (el propio) |
| DELETE | `/users/{id}/` | Super, Administrador |
| PATCH | `/users/{id}/upload-photo/` | Super, Administrador, Estudiante (el propio) |

**Campos principales**

| Campo | Tipo | Descripción |
|---|---|---|
| `email` | string | Único. |
| `dni` | string | Único. Se puede usar para el login. |
| `name`, `last_name` | string | |
| `password` | string | Solo escritura. Se guarda hasheada. |
| `tipo_usuario` | id | Rol del usuario (ver `/user-type/`). |
| `code` | string | Código de operador para firmar operaciones. |

`upload-photo` recibe un `multipart/form-data` con el campo `profile_photo`.

### `/user-type/`

CRUD de los tipos de usuario (Super, Administrador, Consultor, Estudiante). En la práctica se cargan una sola vez con los datos iniciales.

**Roles:** Super, Administrador
