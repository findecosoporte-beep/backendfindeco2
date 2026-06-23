"""Throttling específico para endpoints sensibles."""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """Limita intentos de login y refresh JWT por IP."""

    scope = 'login'


class LoginUserRateThrottle(SimpleRateThrottle):
    """Refuerzo por usuario autenticado en refresh token."""

    scope = 'login_user'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        ident = request.user.pk
        return self.cache_format % {'scope': self.scope, 'ident': ident}
