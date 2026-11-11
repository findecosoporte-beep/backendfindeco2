"""Versión del cache de resumen por cartera: se invalida al cambiar pagos, préstamos o cuotas."""

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

# Sin Redis cada worker de Gunicorn tiene su propio cache y no ve las invalidaciones de los demás.
_CACHE_COMPARTIDO = 'redis' in settings.CACHES['default']['BACKEND'].lower()
RESUMEN_CARTERAS_TTL = 600 if _CACHE_COMPARTIDO else 120
_VERSION_KEY = 'ri_resumen_cartera:version'


def version_resumen_carteras() -> int:
    version = cache.get(_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(_VERSION_KEY, version, timeout=None)
    return int(version)


def _incrementar_version() -> None:
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2, timeout=None)


def invalidar_resumen_carteras() -> None:
    transaction.on_commit(_incrementar_version)
