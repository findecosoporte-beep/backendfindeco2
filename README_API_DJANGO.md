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
- JWT: `POST /api/v1/token/` y `POST /api/v1/token/refresh/`
- Docs: http://127.0.0.1:8000/api/v1/docs/

Header: `Authorization: Bearer <token>`

## Perfil operativo

El JWT usa usuarios de Django; el rol se toma de la tabla `usuarios` por correo igual al email del usuario Django.

## Estructura (solo lo necesario para ejecutar)

| Carpeta / archivo | Uso |
|-------------------|-----|
| `api/` | Modelos, vistas, serializers, URLs, tests |
| `api/migrations/` | Historial de base de datos (no borrar) |
| `config/` | `settings.py`, `urls.py`, WSGI/ASGI |
| `manage.py`, `requirements.txt` | Arranque y dependencias |
| `.env` / `.env.example` | Configuración (local, no subir `.env` a git) |
| `media/` | PDFs y archivos subidos por la app |
| `docs/` | Planes de producción y refactor (documentación) |

Archivos que **no** deben eliminarse: migraciones, `views.py`, `models.py`, `tests.py`, `.env`.

Los `__pycache__` y duplicados en `media/` se regeneran o se ignoran vía `.gitignore`.
