"""Configuración de cache (Redis en producción, LocMem en desarrollo local)."""

import os


def build_caches_config() -> dict:
    redis_url = os.getenv('REDIS_URL', '').strip()
    if redis_url:
        return {
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': redis_url,
                'OPTIONS': {
                    'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                    'SOCKET_CONNECT_TIMEOUT': 5,
                    'SOCKET_TIMEOUT': 5,
                    'IGNORE_EXCEPTIONS': True,
                },
            }
        }

    return {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'findeco-default',
        }
    }
