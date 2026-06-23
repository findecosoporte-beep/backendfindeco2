"""Configuración de producción (App Platform, VM, contenedor)."""

import os

from .base import *  # noqa: F403

DEBUG = False
OPENAPI_ENABLED = env_bool('DJANGO_OPENAPI', default=False)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '').strip()
if not SECRET_KEY:
    raise RuntimeError('DJANGO_SECRET_KEY es obligatorio en producción (DJANGO_ENV=production).')

_railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
if _railway_domain and _railway_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, _railway_domain]

_local_hosts = {'127.0.0.1', 'localhost'}
if not ALLOWED_HOSTS or set(ALLOWED_HOSTS) <= _local_hosts:
    raise RuntimeError(
        'ALLOWED_HOSTS debe incluir el dominio público de la API en producción.'
    )

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0'))
if SECURE_HSTS_SECONDS > 0:
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': os.getenv('THROTTLE_ANON', '30/min'),
    'user': os.getenv('THROTTLE_USER', '200/min'),
    'login': os.getenv('THROTTLE_LOGIN', '10/min'),
    'login_user': os.getenv('THROTTLE_LOGIN_USER', '30/min'),
}

DJANGO_ENABLE_ADMIN = env_bool('DJANGO_ENABLE_ADMIN', default=False)
DJANGO_ADMIN_URL = os.getenv('DJANGO_ADMIN_URL', 'gestion-interna-findeco/').strip() or 'gestion-interna-findeco/'
if not DJANGO_ADMIN_URL.endswith('/'):
    DJANGO_ADMIN_URL += '/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'production': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'production',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
