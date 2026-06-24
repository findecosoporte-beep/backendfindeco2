"""Configuración común Django/DRF para todos los entornos."""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def load_local_env() -> None:
    """Carga variables de entorno desde `.env` si existe (solo desarrollo local)."""
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


def env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    raw = raw.strip('"').strip("'")
    return [
        item.strip().strip('"').strip("'")
        for item in raw.split(',')
        if item.strip()
    ]


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, '').strip().lower()
    if not raw:
        return default
    return raw in ('1', 'true', 'yes')


def mysql_env(name: str, *aliases: str, default: str = '') -> str:
    """Lee variable MySQL; acepta alias de Railway (MYSQLHOST, MYSQLDATABASE, etc.)."""
    for key in (name, *aliases):
        value = os.getenv(key, '').strip()
        if value:
            return value
    return default


def mysql_database_config() -> dict | None:
    """Config Django MySQL desde MYSQL_* o variables nativas de Railway."""
    db_name = mysql_env('MYSQL_DB', 'MYSQLDATABASE', 'BASE_DE_DATOS_MYSQL')
    if not db_name:
        return None

    options: dict = {'charset': 'utf8mb4'}
    if env_bool('MYSQL_SSL'):
        options['ssl'] = {'ssl_mode': 'REQUIRED'}

    return {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': db_name,
        'USER': mysql_env('MYSQL_USER', 'MYSQLUSER', 'USUARIO_DE_MYSQL', default='root'),
        'PASSWORD': mysql_env('MYSQL_PASSWORD', 'MYSQLPASSWORD', 'CONTRASEÑA_DE_MYSQL'),
        'HOST': mysql_env('MYSQL_HOST', 'MYSQLHOST', default='127.0.0.1'),
        'PORT': mysql_env('MYSQL_PORT', 'MYSQLPORT', default='3306'),
        'OPTIONS': options,
    }


load_local_env()

ALLOWED_HOSTS: list[str] = env_list(
    'ALLOWED_HOSTS',
    ['127.0.0.1', 'localhost'],
)

# Railway: dominio público y subdominios *.up.railway.app
_railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip().strip('"').strip("'")
if _railway_domain and _railway_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, _railway_domain]
if os.getenv('RAILWAY_ENVIRONMENT') or _railway_domain:
    for railway_host in ('.up.railway.app', '.railway.app'):
        if railway_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS = [*ALLOWED_HOSTS, railway_host]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'drf_spectacular',
    'django_filters',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

_mysql_config = mysql_database_config()
if _mysql_config:
    DATABASES = {'default': _mysql_config}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-hn'
TIME_ZONE = 'America/Tegucigalpa'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media')))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
        'login': '20/min',
        'login_user': '60/min',
    },
    'DEFAULT_PAGINATION_CLASS': 'api.pagination.StablePageNumberPagination',
    'PAGE_SIZE': 20,
    'PAGE_SIZE_QUERY_PARAM': 'page_size',
    'MAX_PAGE_SIZE': 100,
    'EXCEPTION_HANDLER': 'api.exceptions.custom_exception_handler',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'API Sistema de Prestamos',
    'DESCRIPTION': 'Documentacion OpenAPI.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

CORS_ALLOWED_ORIGINS = env_list(
    'CORS_ALLOWED_ORIGINS',
    [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ],
)
CORS_ALLOW_CREDENTIALS = True

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '60'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS': env_bool('JWT_ROTATE_REFRESH', default=True),
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Sobrescrito en development.py / production.py
DEBUG = False
SECRET_KEY = ''
OPENAPI_ENABLED = False
DJANGO_ENABLE_ADMIN = False
DJANGO_ADMIN_URL = 'admin/'
