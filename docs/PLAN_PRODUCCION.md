# Plan de producción — API FINDECO (Api1)

Documento de referencia para llevar la API Django/DRF de **sistema de préstamos** desde el estado actual (MVP sólido) a un despliegue **seguro, observable y mantenible**.

**Estado actual (resumen):** Django 5.2 + DRF, JWT, roles operativos, OpenAPI, paginación estable, tests + CI básica, MySQL opcional. **Bloqueadores principales:** un solo `settings.py` orientado a dev, `views.py` monolítico (~870 líneas), media local, sin health checks ni pipeline de despliegue.

**Objetivo:** API en producción con HTTPS, secretos gestionados, MySQL gestionado, archivos en almacenamiento externo, logs y alertas mínimas, código modular por dominio.

### Acción inmediata en código (refactor)

Antes o en paralelo a Fase 1 de despliegue, ejecutar el plan de **5 PRs** en `api/`:

→ **[SIGUIENTE_PASO_REFACTOR_API.md](./SIGUIENTE_PASO_REFACTOR_API.md)** (empezar por **Paso 1: `api/core/`**).

---

## Principios del plan

1. **No romper el front** — mantener contratos `/api/v1/`, JWT y formato de error `{ success, error }`.
2. **Entornos separados** — `development`, `staging` (opcional), `production`.
3. **Cambios en fases** — cada fase tiene criterios de aceptación verificables.
4. **Seguridad antes de escalar** — nada público sin `DEBUG=False`, hosts y CORS correctos.

---

## Fase 0 — Preparación (1–2 días)

| # | Tarea | Detalle | Hecho cuando |
|---|--------|---------|--------------|
| 0.1 | Inventario de secretos | Listar: `DJANGO_SECRET_KEY`, MySQL, JWT (si se customiza), CORS origins, dominio front | Checklist en `.env.example` completo |
| 0.2 | Limpiar repo | `.env` y `media/` fuera de git (`.gitignore`); rotar credenciales si alguna estuvo en el repo | `git status` sin `.env` ni PDFs de clientes |
| 0.3 | Baseline de tests | `python manage.py test api` en verde; anotar cobertura actual | CI verde en `main` |
| 0.4 | Definir hosting | Elegir: VM + Nginx, Azure App Service, Container Apps, etc. | Decisión documentada abajo en “Decisión de hosting” |

**Entregable:** rama `chore/production-prep` con `.gitignore` corregido y `.env.example` ampliado.

---

## Fase 1 — Configuración por entorno (2–3 días)

### 1.1 Estructura de settings

```
config/
  settings/
    __init__.py      # DJANGO_SETTINGS_MODULE lee DJANGO_ENV
    base.py          # común: INSTALLED_APPS, REST_FRAMEWORK, etc.
    development.py   # DEBUG=True, SQLite o MySQL local
    production.py    # DEBUG=False, seguridad HTTPS, logging
```

| Variable / ajuste | Development | Production |
|-------------------|-------------|------------|
| `DJANGO_DEBUG` | `true` | `false` (obligatorio) |
| `DJANGO_SECRET_KEY` | dev local | **obligatorio**, sin fallback inseguro |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | dominio API real |
| `CORS_ALLOWED_ORIGINS` | Vite `5173` | URL del front en prod |
| `SECURE_SSL_REDIRECT` | off | on (detrás de proxy) |
| `SESSION_COOKIE_SECURE` / CSRF | según auth | on si hay cookies |
| Swagger `/api/v1/docs/` | abierto | deshabilitado o solo staff |

### 1.2 Variables de entorno (ampliar `.env.example`)

```env
DJANGO_ENV=development
DJANGO_SECRET_KEY=
DJANGO_DEBUG=true
ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

MYSQL_DB=
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_HOST=
MYSQL_PORT=3306

# Producción (Fase 4)
# AZURE_STORAGE_CONNECTION_STRING=
# MEDIA_URL=https://...
```

### 1.3 Criterios de aceptación — Fase 1

- [ ] `DJANGO_ENV=production python manage.py check --deploy` sin errores críticos.
- [ ] Arranque falla si falta `DJANGO_SECRET_KEY` en producción.
- [ ] Front local sigue funcionando con `development`.

---

## Fase 2 — Seguridad y API estable (2–4 días)

| # | Tarea | Acción |
|---|--------|--------|
| 2.1 | JWT | Revisar vida de access/refresh; documentar en README; opcional: blacklist refresh |
| 2.2 | Permisos | Auditar cada `ViewSet`: `required_write_roles` coherente con negocio |
| 2.3 | Throttling | Ajustar rates en prod si hace falta; considerar throttle por IP en login |
| 2.4 | Admin Django | URL no obvia; solo superuser; desactivar en prod si no se usa |
| 2.5 | Usuario operativo | Plan para deprecar `Usuario.clave` legacy; solo Django `User` + perfil `Usuario` |
| 2.6 | Headers | `SECURE_PROXY_SSL_HEADER`, HSTS (tras validar HTTPS), `X_FRAME_OPTIONS` ya OK |

### Tests mínimos a añadir

- Login JWT válido / inválido.
- Rol `asesor` no puede `POST /clientes/` (ya existe — mantener).
- En prod schema: `GET /api/v1/docs/` restringido o 404.

**Criterios de aceptación — Fase 2**

- [ ] Pentest básico manual: sin `DEBUG` no filtra stack traces.
- [ ] Todos los endpoints de escritura exigen JWT + rol correcto.

---

## Fase 3 — Refactor modular (5–8 días, en paralelo con 4 si hay 2 devs)

**Problema:** `api/views.py` y `api/serializers.py` concentran demasiada lógica.

### Estructura objetivo

```
api/
  models.py              # mantener (o split opcional después)
  permissions.py
  exceptions.py
  pagination.py
  urls.py                # router + includes por módulo
  prestamos/
    views.py             # PrestamoViewSet, SimulacionPrestamoView, acciones PDF/reporte
    serializers.py
    services.py          # simulación, plan cuotas, reporte integración
  pagos/
    views.py             # PagoViewSet, hoja semanal
    serializers.py
  clientes/
    views.py
    serializers.py
  catalogos/
    views.py             # Zona, Cartera, Usuario
    serializers.py
  core/
    pdf.py               # factura PDF, utilidades reportlab
```

### Orden de extracción (menor riesgo primero)

1. Utilidades puras (`_round_money`, fechas, PDF) → `core/`.
2. `Zona`, `Cartera`, `Usuario`, `Historial` → `catalogos/`.
3. `Cliente`, documentos → `clientes/`.
4. `Pago` + hoja semanal → `pagos/`.
5. `Prestamo`, simulación, contratos → `prestamos/`.

### Reglas durante el refactor

- **Sin cambiar URLs** públicas (`/api/v1/...`).
- **Un PR por módulo**; tests verdes entre cada merge.
- Lógica de negocio pesada → `services.py`; serializers solo validan/transforman.

**Criterios de aceptación — Fase 3**

- [ ] `views.py` raíz eliminado o < 50 líneas (re-exports).
- [ ] Ningún archivo nuevo > ~400 líneas sin justificación.
- [ ] `python manage.py test api` verde.

---

## Fase 4 — Datos, media y despliegue (4–7 días)

### 4.1 Base de datos

| Item | Producción |
|------|------------|
| Motor | MySQL 8+ gestionado (Azure Database for MySQL, RDS, etc.) |
| Charset | `utf8mb4` (ya en OPTIONS) |
| Migraciones | `migrate` en pipeline antes de levantar app |
| Backups | Automáticos diarios + prueba de restore documentada |

### 4.2 Archivos (media)

| Hoy | Producción |
|-----|------------|
| `MEDIA_ROOT` local | Azure Blob / S3 + `django-storages` |
| Servir con `static()` solo en DEBUG | `MEDIA_URL` CDN o dominio storage |

Pasos: instalar `django-storages`, configurar en `production.py`, migrar PDFs existentes una vez.

### 4.3 Proceso de aplicación

```
Internet → Nginx (TLS) → Gunicorn (workers) → Django WSGI
```

| Componente | Notas |
|------------|--------|
| Gunicorn | `workers = 2*CPU+1`, timeout ≥ generación PDF |
| Nginx | `client_max_body_size` para uploads de documentos |
| Static | `collectstatic` en build; WhiteNoise o Nginx |

### 4.4 Health checks

Añadir endpoints (sin auth o con token interno):

- `GET /api/v1/health/` → `{ "status": "ok" }`
- `GET /api/v1/ready/` → DB `SELECT 1` + opcional storage

**Criterios de aceptación — Fase 4**

- [ ] Subida de documento cliente funciona contra Blob/S3.
- [ ] Health responde 200 en el load balancer.
- [ ] Deploy documentado: build → migrate → restart.

---

## Fase 5 — Observabilidad y CI/CD (3–5 días)

### 5.1 Logging

- Formato JSON en producción.
- Campos: `timestamp`, `level`, `request_id`, `path`, `user_id`, `status`.
- Errores 5xx → nivel ERROR con traceback (solo en logs, no en respuesta).

### 5.2 CI (ampliar `.github/workflows/ci.yml`)

```yaml
# Objetivo del pipeline
- pip install -r requirements.txt
- ruff check api config   # añadir ruff
- python manage.py check
- python manage.py test api --verbosity=2
# opcional: migrate --plan contra MySQL service container
```

### 5.3 CD (según hosting)

| Paso | Acción |
|------|--------|
| Build | Imagen Docker o artefacto + `collectstatic` |
| Staging | Deploy automático en merge a `main` (opcional) |
| Production | Deploy manual aprobado o tag `v*` |

### 5.4 Alertas mínimas

- Tasa 5xx > umbral.
- Disco / conexiones MySQL.
- Certificado TLS próximo a vencer (si Nginx propio).

**Criterios de aceptación — Fase 5**

- [ ] Un error simulado aparece en logs estructurados.
- [ ] PR sin tests/lint no puede mergear (branch protection).

---

## Fase 6 — Calidad y documentación (continuo)

| # | Tarea | Meta |
|---|--------|------|
| 6.1 | Cobertura tests | ≥ 70% en `serializers` + `services` críticos (préstamo, pago, permisos) |
| 6.2 | OpenAPI | Mantener `drf-spectacular`; publicar schema solo en staging |
| 6.3 | README | Sección “Producción” con variables, Gunicorn, migrate, rollback |
| 6.4 | Runbook | Incidentes: DB caída, JWT expirado masivo, storage lleno |

---

## Cronograma sugerido (1 desarrollador)

| Semana | Fases | Hito |
|--------|--------|------|
| 1 | 0 + 1 + inicio 2 | Settings prod + check --deploy |
| 2 | 2 + 3 (catálogos, clientes) | Seguridad + primeros módulos |
| 3 | 3 (prestamos, pagos) + 4 inicio | Refactor completo + MySQL staging |
| 4 | 4 + 5 | Deploy staging + health + CI |
| 5 | 5 + 6 + UAT | Producción con front real + monitoreo |

Con **2 desarrolladores**, Fases 3 y 4 pueden solaparse (ahorro ~1 semana).

---

## Decisión de hosting (rellenar)

| Opción | Pros | Contras |
|--------|------|---------|
| **Azure App Service** | Integración Microsoft, fácil HTTPS | Coste, PDF CPU-bound |
| **VM + Nginx + Gunicorn** | Control total | Ops manual |
| **Azure Container Apps** | Escala, Docker | Más setup inicial |

**Recomendación inicial:** App Service o Container Apps + Azure Database for MySQL + Azure Blob Storage (alineado con skills Azure del equipo).

---

## Checklist final “listo para producción”

Marcar todo antes de abrir tráfico real:

- [ ] `DEBUG=False`, `SECRET_KEY` fuerte, `ALLOWED_HOSTS` correcto
- [ ] HTTPS terminado y probado end-to-end con el front
- [ ] MySQL prod con backups
- [ ] Media en almacenamiento externo
- [ ] `.env` nunca en el repositorio
- [ ] `python manage.py test api` en CI
- [ ] Health/ready en load balancer
- [ ] Logs centralizados consultables
- [ ] Swagger restringido o desactivado en prod
- [ ] Plan de rollback (migración reversa o backup restore)
- [ ] Prueba manual: alta préstamo → plan cuotas → cobro → PDF

---

## Fuera de alcance (por ahora)

- Microservicios separados.
- GraphQL.
- Reescritura en Go.
- Multi-tenant por schema.
- OpenTelemetry completo (Fase 5+ opcional).

---

## Referencias en el repo

| Archivo | Rol |
|---------|-----|
| `config/settings.py` | Migrar a `config/settings/*` |
| `api/views.py` | Dividir según Fase 3 |
| `api/permissions.py` | Mantener; auditar roles |
| `api/exceptions.py` | Mantener formato de error |
| `.github/workflows/ci.yml` | Ampliar en Fase 5 |
| `README_API_DJANGO.md` | Ampliar con sección producción |

---

*Última actualización: plan inicial post-revisión de arquitectura. Ajustar fechas según capacidad del equipo.*
