"""
Selección de settings según DJANGO_ENV.

- development (por defecto): DEBUG, OpenAPI, SQLite/MySQL local.
- production: seguridad reforzada, SECRET_KEY y ALLOWED_HOSTS obligatorios.

Compatibilidad: si DJANGO_ENV no está definido y DJANGO_DEBUG=false, usa production
(comportamiento de App Platform con solo DJANGO_DEBUG).
"""

import os

from .base import *  # noqa: F403

_env = os.getenv('DJANGO_ENV', '').strip().lower()
if not _env:
    _debug = os.getenv('DJANGO_DEBUG', 'true').lower() in ('1', 'true', 'yes')
    _env = 'development' if _debug else 'production'

if _env == 'production':
    from .production import *  # noqa: F403
elif _env == 'development':
    from .development import *  # noqa: F403
else:
    raise RuntimeError(f'DJANGO_ENV no reconocido: "{_env}". Use development o production.')
