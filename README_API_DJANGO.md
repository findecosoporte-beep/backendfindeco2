# API Django - Sistema de Prestamos (Api1)

## Instalacion

```bash
cd Api1
pip install -r requirements.txt
```

## MySQL (opcional)

Copia `.env.example` a `.env` y ajusta credenciales. Sin `MYSQL_DB` usa SQLite local.

## Ejecutar

### Modo fácil (oficina, sin CMD manual)

En la carpeta raíz del proyecto (junto a `Api1` y `front`):

- **Primera vez:** **`Instalar-FINDECO.bat`** — dependencias, base de datos, icono en escritorio.
- **Cada día:** icono **FINDECO** o **`Iniciar-FINDECO.bat`** — API + pantalla + navegador.
- **`Detener-FINDECO.bat`** — apaga puertos 8000 y 5173.

Guía completa: [INICIAR_FINDECO.md](../INICIAR_FINDECO.md).

### Modo desarrollador (terminal)

```bash
python manage.py migrate
python manage.py runserver
```

En otra terminal, en `front/`: `npm run dev`.

- Raiz redirige a Swagger: http://127.0.0.1:8000/
- API: http://127.0.0.1:8000/api/v1/
## Autenticación JWT

- Login: `POST /api/v1/token/` con `username` y `password` (usuario Django).
- Refresh: `POST /api/v1/token/refresh/` con `refresh`.
- Header en peticiones: `Authorization: Bearer <access_token>`.

### Duración de tokens (variables opcionales en `.env`)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `JWT_ACCESS_MINUTES` | 60 | Vida del access token |
| `JWT_REFRESH_DAYS` | 7 | Vida del refresh token |
| `JWT_ROTATE_REFRESH` | true | Emite refresh nuevo al renovar |

### Rate limit en login

Los endpoints `/token/` y `/token/refresh/` tienen throttle dedicado (`login`, `login_user`) para mitigar fuerza bruta. En producción los límites son más estrictos (ver `config/settings/production.py`).

## Perfil operativo

El JWT usa usuarios de Django; el rol se toma de la tabla `usuarios` por correo igual al email del usuario Django.

El campo `usuarios.clave` está **deprecado** (legacy). No usar para login; solo cuenta Django + JWT.

## Roles y permisos de escritura

Matriz centralizada en `api/role_policy.py` (alineada con `front/src/composables/usePermissions.ts`):

| Recurso | Roles con escritura |
|---------|---------------------|
| Clientes, préstamos, catálogos | administrador, supervisor |
| Pagos / cobros | + asesor, cobranza_adm_jud |
| Documentos cliente | + asesor, cobranza_adm_jud |
| Contratos | + asesor |

## Admin Django

- **Desarrollo:** `/admin/` activo.
- **Producción:** desactivado por defecto. Para habilitar: `DJANGO_ENABLE_ADMIN=true` y `DJANGO_ADMIN_URL` con ruta no obvia.

## Estructura (solo lo necesario para ejecutar)

| Carpeta / archivo               | Uso                                             |
| ---------------------------------| -------------------------------------------------|
| `api/`                          | Modelos, vistas, serializers, URLs, tests       |
| `api/role_policy.py`            | Matriz de roles de escritura                    |
| `api/migrations/`               | Historial de base de datos (no borrar)          |
| `config/settings/`              | `base.py`, `development.py`, `production.py`    |
| `config/urls.py`                | Rutas, JWT con throttle, admin condicional      |
| `manage.py`, `requirements.txt` | Arranque y dependencias                         |
| `.env` / `.env.example`         | Configuración (local, no subir `.env` a git)    |
| `media/`                        | PDFs y archivos subidos por la app              |
| `docs/`                         | Planes de producción y refactor (documentación) |

Archivos que **no** deben eliminarse: migraciones, `views.py`, `models.py`, `tests.py`, `.env`.

Los `__pycache__` y duplicados en `media/` se regeneran o se ignoran vía `.gitignore`.
