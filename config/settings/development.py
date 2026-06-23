"""Configuración local de desarrollo."""

import os

from .base import *  # noqa: F403

DEBUG = True
OPENAPI_ENABLED = True

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    SECRET_KEY = 'django-insecure-dev-only-change-in-production'

# En dev no forzar HTTPS ni cookies seguras
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

DJANGO_ENABLE_ADMIN = True
DJANGO_ADMIN_URL = os.getenv('DJANGO_ADMIN_URL', 'admin/').strip() or 'admin/'
if not DJANGO_ADMIN_URL.endswith('/'):
    DJANGO_ADMIN_URL += '/'
