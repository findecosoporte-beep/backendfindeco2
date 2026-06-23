# Despliegue en Railway con MySQL

Guía para conectar la API Django al MySQL del mismo proyecto en [Railway](https://railway.com/).

## 1. Crear el proyecto

1. Entra a [railway.com](https://railway.com/) → **New Project**
2. **Deploy from GitHub repo** → `findecosoporte-beep/backendfindeco2`
3. Railway detecta Python, `railway.toml`, `Procfile` y `requirements.txt`

## 2. Añadir MySQL

1. En el proyecto → **+ New** → **Database** → **Add MySQL**
2. Espera a que el servicio MySQL quede en estado **Active**

## 3. Conectar la API a MySQL

1. Abre el servicio **web** (tu API, no el de MySQL)
2. Pestaña **Variables**
3. Pulsa **+ New Variable** → **Add Reference**
4. Selecciona el servicio **MySQL** y marca estas variables:

| Variable Railway | Uso en Django |
|------------------|---------------|
| `MYSQLHOST` | Host de la base |
| `MYSQLPORT` | Puerto |
| `MYSQLUSER` | Usuario |
| `MYSQLPASSWORD` | Contraseña |
| `MYSQLDATABASE` | Nombre de la BD |

La API las lee automáticamente (no necesitas renombrarlas a `MYSQL_HOST`, etc.).

## 4. Variables obligatorias de la API

Añade también (como **valor fijo**, no referencia):

```env
DJANGO_ENV=production
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<genera una clave larga aleatoria>
DJANGO_SECURE_SSL_REDIRECT=false
CORS_ALLOWED_ORIGINS=https://tu-frontend.com
```

`ALLOWED_HOSTS` es opcional: si Railway define `RAILWAY_PUBLIC_DOMAIN`, la API lo agrega sola.

## 5. Dominio público

1. Servicio web → **Settings** → **Networking**
2. **Generate Domain** (ej. `backendfindeco2-production.up.railway.app`)
3. Prueba: `https://TU-DOMINIO/api/v1/health/` → debe responder `{"status":"ok"}`

## 6. Migraciones

Al arrancar, `scripts/start.sh` ejecuta `python manage.py migrate --noinput` contra MySQL.

Revisa los **Deploy Logs** la primera vez; debe aparecer algo como `Applying api.0001_initial...`.

## 7. Crear usuario administrador (opcional)

En el servicio web → **Settings** → abre una **Railway Shell** o usa **Run command**:

```bash
python manage.py createsuperuser
```

Para login JWT necesitas un usuario Django vinculado al perfil en tabla `usuarios`.

## Resolución de problemas

| Error | Solución |
|-------|----------|
| `Repository not found` | Repo privado o cuenta GitHub incorrecta |
| `DJANGO_SECRET_KEY es obligatorio` | Añade la variable en Railway |
| `ALLOWED_HOSTS debe incluir...` | Genera dominio en Networking o define `ALLOWED_HOSTS` |
| `Can't connect to MySQL` | Verifica referencias MYSQL* en Variables del servicio web |
| `Access denied` | Revisa que las referencias apunten al servicio MySQL correcto |

## Nota sobre archivos (media/)

Los PDFs subidos se guardan en disco del contenedor. En Railway ese disco es **temporal**. Para producción estable, planifica volumen persistente o almacenamiento externo (S3, etc.).
