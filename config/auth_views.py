"""Vistas JWT con rate limiting, bloqueo por intentos y auditoría."""

import logging

from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_client_ip_address
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.throttling import LoginRateThrottle, LoginUserRateThrottle

logger = logging.getLogger('api.auth')

LOCKOUT_MESSAGE = (
    'Demasiados intentos fallidos. Espere un momento antes de volver a intentar.'
)


def _login_credentials(request) -> dict[str, str]:
    data = getattr(request, 'data', None) or {}
    return {
        'username': str(data.get('username', '')).strip(),
        'password': str(data.get('password', '')),
    }


def _client_ip(request) -> str:
    return get_client_ip_address(request) or 'desconocida'


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login JWT: throttle por IP + bloqueo axes + registro de intentos."""

    throttle_classes = (LoginRateThrottle,)

    def post(self, request, *args, **kwargs):
        credentials = _login_credentials(request)
        username = credentials['username']
        ip = _client_ip(request)

        if AxesProxyHandler.is_locked(request, credentials):
            logger.warning(
                'Login bloqueado por intentos fallidos username=%s ip=%s',
                username,
                ip,
            )
            return Response({'detail': LOCKOUT_MESSAGE}, status=status.HTTP_403_FORBIDDEN)

        response = super().post(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            logger.info('Login exitoso username=%s ip=%s', username, ip)
            AxesProxyHandler.reset_attempts(ip_address=ip, username=username)
        elif response.status_code == status.HTTP_401_UNAUTHORIZED:
            logger.warning('Login fallido username=%s ip=%s', username, ip)
            AxesProxyHandler.user_login_failed(
                sender=self.__class__,
                credentials=credentials,
                request=request,
            )

        return response


class ThrottledTokenRefreshView(TokenRefreshView):
    """Refresh JWT: throttle por IP y por usuario."""

    throttle_classes = (LoginRateThrottle, LoginUserRateThrottle)
